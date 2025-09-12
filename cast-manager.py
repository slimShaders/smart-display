#!/usr/bin/env python3
"""
Smart Display Cast Manager
Automatically discovers Nest Hub and manages casting from Raspberry Pi
"""

import subprocess
import time
import logging
import json
import socket
import threading
from datetime import datetime, timedelta
import signal
import sys
import os
import urllib.request
import urllib.error

class CastManager:
    def __init__(self):
        self.nest_hub_ip = None
        self.nest_hub_hostname = "nest-hub"
        self.server_port = 5500
        self.server_container_name = "smart-display-server"
        self.last_cast_time = None
        self.network_scan_interval = 60  # 1 minute
        self.running = True
        self.cache_file = "/opt/smart-display/device_cache.json"
        self.last_ip_verification = datetime.min
        
        # Setup logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('/var/log/cast-manager.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def load_cached_ip(self):
        """Load cached device IP from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    cached_ip = cache_data.get('nest_hub_ip')
                    cached_time = cache_data.get('last_seen')
                    
                    if cached_ip and cached_time:
                        last_seen = datetime.fromisoformat(cached_time)
                        # Use cached IP if it was seen within the last 24 hours
                        if datetime.now() - last_seen < timedelta(hours=24):
                            self.logger.info(f"Loaded cached IP: {cached_ip}")
                            return cached_ip
                        else:
                            self.logger.info("Cached IP too old, will rescan")
                    else:
                        self.logger.debug("Invalid cache data")
            else:
                self.logger.debug("No cache file found")
        except Exception as e:
            self.logger.warning(f"Failed to load cache: {e}")
        
        return None

    def save_cached_ip(self, ip):
        """Save device IP to cache file"""
        try:
            cache_data = {
                'nest_hub_ip': ip,
                'last_seen': datetime.now().isoformat(),
                'hostname': self.nest_hub_hostname
            }
            
            # Ensure cache directory exists
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            self.logger.debug(f"Cached IP {ip} to {self.cache_file}")
            
        except Exception as e:
            self.logger.warning(f"Failed to save cache: {e}")

    def verify_cached_ip(self, ip):
        """Verify that cached IP is still valid"""
        try:
            # Quick ping test
            result = subprocess.run(
                f"ping -c 1 -W 2 {ip}", 
                shell=True, 
                capture_output=True, 
                timeout=5
            )
            
            if result.returncode == 0:
                # Ping successful, now verify it's still a Chromecast
                return self.check_chromecast_device(ip)
            else:
                self.logger.debug(f"Cached IP {ip} not responding to ping")
                return False
                
        except Exception as e:
            self.logger.debug(f"IP verification failed: {e}")
            return False

    def get_local_ip(self):
        """Get the local IP address of this device"""
        try:
            # Connect to a remote address to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e:
            self.logger.error(f"Failed to get local IP: {e}")
            return None

    def get_network_range(self):
        """Get the network range for scanning"""
        local_ip = self.get_local_ip()
        if not local_ip:
            return None
        
        # Assume /24 network
        ip_parts = local_ip.split('.')
        network_base = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}"
        return network_base

    def scan_for_nest_hub(self):
        """Scan network for Chromecast/Nest Hub devices with Google MAC addresses"""
        self.logger.info("Scanning network for Nest Hub...")
        
        network_base = self.get_network_range()
        if not network_base:
            self.logger.error("Could not determine network range")
            return None

        try:
            cmd = f"nmap -Pn -p 8008,8009 --open {network_base}.1-254"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                self.logger.warning("nmap not available, trying alternative scan...")
                return self.scan_for_nest_hub_alternative()
            
            # Parse nmap output for Google devices with Chromecast ports
            google_devices = self.parse_nmap_for_google_devices(result.stdout)
            
            if google_devices:
                # Verify each device using CATT
                for ip in google_devices:
                    if self.check_chromecast_device(ip):
                        self.logger.info(f"Found verified Nest Hub/Chromecast at {ip}")
                        return ip
                
                # If CATT check fails, return the first Google device found
                self.logger.info(f"Found Google device at {google_devices[0]} (CATT verification failed)")
                return google_devices[0]
            else:
                self.logger.warning("No Google devices with Chromecast ports found")
                    
        except subprocess.TimeoutExpired:
            self.logger.warning("Network scan timed out")
        except Exception as e:
            self.logger.error(f"Network scan failed: {e}")
        
        return None

    def parse_nmap_for_google_devices(self, nmap_output):
        """Parse nmap output to find devices with Google MAC addresses and Chromecast ports"""
        google_devices = []
        current_ip = None
        has_chromecast_ports = False
        is_google_device = False
        
        for line in nmap_output.split('\n'):
            line = line.strip()
            
            # New scan report starts
            if 'Nmap scan report for' in line:
                # Save previous device if it was valid
                if current_ip and has_chromecast_ports and is_google_device:
                    google_devices.append(current_ip)
                
                # Reset for new device
                current_ip = line.split()[-1].strip('()')
                has_chromecast_ports = False
                is_google_device = False
                
            # Check for Chromecast ports
            elif current_ip and ('8008/tcp open' in line or '8009/tcp open' in line):
                has_chromecast_ports = True
                
            # Check for Google MAC address
            elif current_ip and 'MAC Address:' in line and 'Google' in line:
                is_google_device = True
                self.logger.debug(f"Found Google device at {current_ip}: {line}")
        
        # Don't forget the last device
        if current_ip and has_chromecast_ports and is_google_device:
            google_devices.append(current_ip)
            
        self.logger.info(f"Found {len(google_devices)} Google device(s) with Chromecast ports: {google_devices}")
        return google_devices

    def scan_for_nest_hub_alternative(self):
        """Alternative scan method using ping"""
        self.logger.info("Using ping-based network scan...")
        network_base = self.get_network_range()
        if not network_base:
            return None

        active_ips = []
        
        # Ping common IP ranges
        for i in range(1, 255):
            ip = f"{network_base}.{i}"
            try:
                result = subprocess.run(
                    f"ping -c 1 -W 1 {ip}", 
                    shell=True, 
                    capture_output=True, 
                    timeout=2
                )
                if result.returncode == 0:
                    active_ips.append(ip)
            except:
                continue
        
        # Check hostnames
        for ip in active_ips:
            if self.check_hostname(ip):
                self.logger.info(f"Found Nest Hub at {ip}")
                return ip
        
        return None

    def check_hostname(self, ip):
        """Check if IP has the target hostname"""
        try:
            hostname = socket.gethostbyaddr(ip)[0].lower()
            return self.nest_hub_hostname.lower() in hostname
        except:
            # Try alternative methods for Chromecast devices
            return self.check_chromecast_device(ip)

    def check_chromecast_device(self, ip):
        """Check if device at IP is a Chromecast/Nest Hub using CATT"""
        try:
            cmd = f"catt -d {ip} status"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                output = result.stdout.lower()
                # Look for common Nest Hub / Chromecast indicators
                nest_indicators = [
                    "nest hub", "google nest", "living room", "display", 
                    "chromecast", "cast", "backdrop", "idle", "ready"
                ]
                
                if any(indicator in output for indicator in nest_indicators):
                    self.logger.info(f"Found Chromecast device at {ip}: {result.stdout.strip()}")
                    return True
                
        except subprocess.TimeoutExpired:
            self.logger.debug(f"Chromecast check timed out for {ip}")
        except Exception as e:
            self.logger.debug(f"Chromecast check failed for {ip}: {e}")
        
        return False

    def ensure_docker_running(self):
        """Ensure Docker is running"""
        try:
            result = subprocess.run("docker info", shell=True, capture_output=True)
            if result.returncode != 0:
                self.logger.error("Docker is not running")
                return False
            return True
        except Exception as e:
            self.logger.error(f"Docker check failed: {e}")
            return False

    def start_web_server(self):
        """Start the HTTP server if not already running"""
        try:
            # Check if container is already running
            cmd = f"docker ps --filter name={self.server_container_name} --format '{{{{.Names}}}}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if self.server_container_name in result.stdout:
                self.logger.info("Web server already running")
                return True
            
            # Start the server
            local_ip = self.get_local_ip()
            if not local_ip:
                self.logger.error("Cannot determine local IP for web server")
                return False
            
            install_dir = "/opt/smart-display"
            src_path = f"{install_dir}/src"
            
            cmd = (f"docker run -d --name {self.server_container_name} "
                   f"-p {self.server_port}:80 "
                   f"-v {src_path}:/usr/local/apache2/htdocs/ "
                   f"httpd:alpine")
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.logger.info(f"Web server started on {local_ip}:{self.server_port}")
                time.sleep(2)  # Give server time to start
                return True
            else:
                self.logger.error(f"Failed to start web server: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting web server: {e}")
            return False

    def cast_to_device(self):
        """Cast the website to the Nest Hub"""
        if not self.nest_hub_ip:
            self.logger.error("No Nest Hub IP available for casting")
            return False
        
        local_ip = self.get_local_ip()
        if not local_ip:
            self.logger.error("Cannot determine local IP for casting")
            return False
        
        cast_url = f"http://{local_ip}:{self.server_port}/"
        
        try:
            cmd = f"catt -d {self.nest_hub_ip} cast_site {cast_url}"
            
            self.logger.info(f"Casting {cast_url} to {self.nest_hub_ip}...")
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.logger.info(f"Cast initiated: {result.stdout.strip()}")
                self.last_cast_time = datetime.now()
                return True
            else:
                self.logger.error(f"Casting failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.error("Casting command timed out")
            return False
        except Exception as e:
            self.logger.error(f"Casting error: {e}")
            return False

    def check_cast_status(self):
        """Check if our content is still being displayed on the Nest Hub"""
        if not self.nest_hub_ip:
            return False
            
        try:
            # Get detailed device info using CATT
            cmd = f"catt -d {self.nest_hub_ip} info"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                self.logger.warning(f"Failed to get device info: {result.stderr}")
                return False
            
            info_output = result.stdout.strip()
            self.logger.debug(f"Device info: {info_output}")
            
            # Check if DashCast (web browser) app is active
            if "display_name: DashCast" in info_output:
                # DashCast is running - this means web content is being displayed
                
                # Check if it's our content by looking for our server IP in a content check
                local_ip = self.get_local_ip()
                if local_ip:
                    # If DashCast is active and we have our IP, assume it's our content
                    # (In practice, you might want to add more sophisticated checking)
                    self.logger.debug("DashCast app is active - assuming our content is displayed")
                    return True
                
            # Check for other indicators that might suggest our content is active
            if any(indicator in info_output.lower() for indicator in [
                "status_text: Application ready",
                "app_id: 84912283"  # DashCast app ID
            ]):
                # DashCast app is loaded, likely showing web content
                return True
            
            # If we reach here, likely no web content or different app
            self.logger.debug("No DashCast app detected or device idle")
            return False
            
        except subprocess.TimeoutExpired:
            self.logger.warning("Device info check timed out")
            return False
        except Exception as e:
            self.logger.debug(f"Cast status check failed: {e}")
            return False

    def check_web_server_health(self):
        """Check if our web server is responding"""
        local_ip = self.get_local_ip()
        if not local_ip:
            return False
        
        try:
            url = f"http://{local_ip}:{self.server_port}/"
            response = urllib.request.urlopen(url, timeout=5)
            return response.getcode() == 200
        except Exception as e:
            self.logger.debug(f"Web server health check failed: {e}")
            return False

    def trigger_recast(self):
        """Trigger a recast to the device
        
        TODO: Add your custom recast logic here
        This could include stopping current content, waiting, then recasting
        """
        # Entry point for custom recast logic - implement your own here
        return self.cast_to_device()

    def cleanup_containers(self):
        """Clean up any hanging containers"""
        try:
            # Remove old containers
            subprocess.run(f"docker rm -f {self.server_container_name} 2>/dev/null", shell=True)
            subprocess.run(f"docker container prune -f", shell=True)
        except:
            pass

    def run(self):
        """Main execution loop"""
        self.logger.info("Starting Cast Manager...")
        
        if not self.ensure_docker_running():
            self.logger.error("Docker is not available, exiting")
            return 1
        
        self.cleanup_containers()
        
        last_network_scan = datetime.min
        
        while self.running:
            try:
                now = datetime.now()
                
                # Initialize status variables
                web_server_ok = True
                cast_status_ok = True
                
                # First, check if everything is working fine - if so, do nothing
                if self.nest_hub_ip:
                    # Quick health check: web server + casting status
                    web_server_ok = self.check_web_server_health()
                    cast_status_ok = self.check_cast_status()
                    
                    if web_server_ok and cast_status_ok:
                        self.logger.debug("All systems healthy - no action needed")
                        time.sleep(30)  # Everything working, just wait
                        continue
                    else:
                        if not web_server_ok:
                            self.logger.info("Web server issue detected")
                        if not cast_status_ok:
                            self.logger.info("Cast status issue detected")
                
                # Try to get IP from cache first, then scan if needed
                if not self.nest_hub_ip:
                    # First try to load from cache
                    cached_ip = self.load_cached_ip()
                    if cached_ip:
                        self.logger.info("Trying cached IP...")
                        if self.verify_cached_ip(cached_ip):
                            self.logger.info(f"Cached IP {cached_ip} verified successfully")
                            self.nest_hub_ip = cached_ip
                            self.last_ip_verification = now
                        else:
                            self.logger.info("Cached IP verification failed, will scan network")
                
                # Only do expensive operations if we don't have a valid IP or there are issues
                if not self.nest_hub_ip:
                    self.logger.info("No device IP - scanning network...")
                    discovered_ip = self.scan_for_nest_hub()
                    if discovered_ip:
                        self.logger.info(f"Nest Hub IP found: {discovered_ip}")
                        self.nest_hub_ip = discovered_ip
                        self.save_cached_ip(discovered_ip)  # Cache the new IP
                        self.last_ip_verification = now
                    else:
                        self.logger.warning("Nest Hub not found on network")
                        time.sleep(30)  # Wait before trying again
                        continue
                    
                    last_network_scan = now
                
                # Periodic IP verification (only if we haven't checked recently and there are issues)
                elif now - self.last_ip_verification > timedelta(minutes=10):
                    self.logger.debug("Periodic IP verification...")
                    if not self.verify_cached_ip(self.nest_hub_ip):
                        self.logger.info("IP verification failed - device may have changed")
                        self.nest_hub_ip = None
                        continue  # Will trigger scan on next iteration
                    else:
                        self.last_ip_verification = now
                
                # Handle issues: restart web server and/or recast
                if self.nest_hub_ip:
                    # Check if web server needs to be started/restarted
                    if not self.start_web_server():
                        self.logger.error("Failed to start web server")
                        time.sleep(30)
                        continue
                    
                    # Check if we need to recast (either initial cast or detected issue)
                    need_to_cast = (
                        not self.last_cast_time or  # Initial cast
                        not cast_status_ok  # Cast status issue detected
                    )
                    
                    if need_to_cast:
                        if not self.last_cast_time:
                            self.logger.info("Performing initial cast...")
                        else:
                            self.logger.info("Recasting due to status issue...")
                        
                        success = self.cast_to_device()
                        if not success:
                            self.logger.error("Failed to cast, will retry next cycle")
                        else:
                            # Reset the status check variables since we just cast
                            cast_status_ok = True
                
                # TODO: Add your custom monitoring logic here
                # This is where you can add periodic checks for:
                # - Cast status monitoring
                # - Automatic recasting
                # - Health checks
                # 
                # Example entry points:
                # if should_check_status():
                #     if not self.check_cast_status():
                #         self.trigger_recast()
                
                time.sleep(30)  # Main loop delay
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(30)
        
        self.logger.info("Cast Manager shutting down...")
        self.cleanup_containers()
        return 0

if __name__ == "__main__":
    manager = CastManager()
    exit_code = manager.run()
    sys.exit(exit_code)
