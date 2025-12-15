const tg = window.Telegram.WebApp;
tg.expand();
tg.MainButton.textColor = '#FFFFFF';
tg.MainButton.color = '#2ecc71';

// Savollar bazasi
const questionsData = [
    { q: "HTML qanday tushuniladi?", a: ["Hyper Text Markup Language", "Home Tool Markup Language", "Hyperlinks and Text Marking"], c: 0 },
    { q: "CSS nima uchun ishlatiladi?", a: ["Ma'lumotlar bazasi", "Veb sahifa dizayni", "Serverni boshqarish"], c: 1 },
    { q: "JavaScript qayerda ishlaydi?", a: ["Faqat Serverda", "Faqat Brauzerda", "Brauzer va Serverda"], c: 2 },
    { q: "Eng katta sarlavha qaysi?", a: ["h6", "h1", "head"], c: 1 },
    { q: "<a> tegi nima vazifani bajaradi?", a: ["Rasm qo'yish", "Havola (link) yaratish", "Matnni qalin qilish"], c: 1 }
];

function startTest() {
    const name = document.getElementById("name").value.trim();
    const group = document.getElementById("group").value.trim();
    
    if (!name || !group) {
        tg.showAlert("Iltimos, ism va guruhni to'liq kiriting!");
        return;
    }

    // Ekranni almashtirish
    document.getElementById("login-screen").style.display = "none";
    const quizScreen = document.getElementById("quiz-screen");
    quizScreen.style.display = "block";
    quizScreen.classList.add("fade-in");
    
    renderQuestions();
}

function renderQuestions() {
    const container = document.getElementById("questions-container");
    container.innerHTML = "";

    questionsData.forEach((item, index) => {
        let html = `
        <div class="question-block">
            <div class="question-text">${index + 1}. ${item.q}</div>
            <div class="options">
        `;
        
        item.a.forEach((opt, i) => {
            // Har bir variant uchun unikal ID
            const inputId = `q${index}_opt${i}`;
            
            html += `
            <label class="option-label" onclick="selectOption(this, 'q${index}')">
                <span class="option-circle"></span>
                <input type="radio" name="q${index}" value="${i}">
                <span>${opt}</span>
            </label>`;
        });
        
        html += `</div></div>`;
        container.innerHTML += html;
    });
}

// Variant tanlanganda rangini o'zgartirish funksiyasi
function selectOption(label, questionName) {
    // Avval shu savoldagi barcha belgilarni tozalaymiz
    const allLabels = document.querySelectorAll(`input[name="${questionName}"]`);
    allLabels.forEach(input => {
        input.parentElement.classList.remove("selected");
    });

    // Bosilganini belgilaymiz
    label.classList.add("selected");
    // Radio inputni ham belgilab qo'yamiz (xavfsizlik uchun)
    const radio = label.querySelector("input");
    radio.checked = true;
}

function finishTest() {
    let score = 0;
    let unanswered = false;

    questionsData.forEach((item, index) => {
        const checked = document.querySelector(`input[name="q${index}"]:checked`);
        if (checked) {
            if (parseInt(checked.value) === item.c) score++;
        } else {
            unanswered = true;
        }
    });

    if (unanswered) {
        tg.showConfirm("Barcha savollarga javob bermadingiz. Baribir yakunlaymizmi?", (confirm) => {
            if (confirm) sendData(score);
        });
    } else {
        sendData(score);
    }
}

function sendData(score) {
    const data = {
        name: document.getElementById("name").value,
        group: document.getElementById("group").value,
        score: score,
        total: questionsData.length
    };
    
    tg.sendData(JSON.stringify(data));
}
