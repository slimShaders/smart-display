const hebrewDays = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'];

const hebrewMonths = [
    'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
    'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר'
];

const greetings = {
    morning: 'בוקר טוב',
    afternoon: 'צהריים טובים',
    evening: 'ערב טוב',
    night: 'לילה טוב'
};

const messages = [
    'יום נהדר לך!',
    'יום מקסים!',
];

function updateTimeAndDate() {
    const now = new Date();
    
    const timeString = now.toLocaleTimeString('he-IL', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    });
    document.getElementById('time').textContent = timeString;
    
    const dayOfWeek = now.getDay();
    document.getElementById('day').textContent = `היום יום ${hebrewDays[dayOfWeek]}`;
    
    const hour = now.getHours();
    const day = now.getDate();
    const month = now.getMonth();
    const year = now.getFullYear();
    const dateString = `ה-${day} ל${hebrewMonths[month]} ${year}`;
    document.getElementById('date').textContent = dateString;
    
    let greeting;
    if (hour >= 5 && hour < 12) {
        greeting = greetings.morning;
    } else if (hour >= 12 && hour < 17) {
        greeting = greetings.afternoon;
    } else if (hour >= 17 && hour < 22) {
        greeting = greetings.evening;
    } else {
        greeting = greetings.night;
    }
    document.getElementById('greeting').textContent = greeting;
}

function updateMessage() {
    const randomMessage = messages[Math.floor(Math.random() * messages.length)];
    document.getElementById('message').textContent = randomMessage;
}

function init() {
    updateTimeAndDate();
    updateMessage();
    
    setInterval(updateTimeAndDate, 1000);
    
    setInterval(updateMessage, 10 * 60 * 1000);
}

document.addEventListener('DOMContentLoaded', init);