const tg = window.Telegram.WebApp;
tg.expand();

const questionsData = [
    { q: "2 + 2 = ?", a: ["3", "4", "5"], c: 1 },
    { q: "O'zbekiston poytaxti?", a: ["Samarqand", "Toshkent", "Buxoro"], c: 1 },
    { q: "Python nima?", a: ["Ilon", "Dasturlash tili", "Mashina"], c: 1 },
    { q: "Apple asoschisi?", a: ["Steve Jobs", "Bill Gates", "Elon Musk"], c: 0 },
    { q: "Eng katta okean?", a: ["Tinch", "Atlantika", "Hind"], c: 0 }
];

function startTest() {
    const name = document.getElementById("name").value;
    const group = document.getElementById("group").value;
    if (!name || !group) { alert("Ism va Guruhni kiriting!"); return; }
    
    document.getElementById("login-form").classList.add("hidden");
    document.getElementById("quiz-form").classList.remove("hidden");
    
    const qDiv = document.getElementById("questions");
    questionsData.forEach((item, index) => {
        let html = `<div class="question"><p>${index+1}. ${item.q}</p>`;
        item.a.forEach((opt, i) => {
            html += `<label><input type="radio" name="q${index}" value="${i}"> ${opt}</label><br>`;
        });
        html += `</div>`;
        qDiv.innerHTML += html;
    });
}

function finishTest() {
    let score = 0;
    questionsData.forEach((item, index) => {
        const checked = document.querySelector(`input[name="q${index}"]:checked`);
        if (checked && parseInt(checked.value) === item.c) score++;
    });

    const data = {
        name: document.getElementById("name").value,
        group: document.getElementById("group").value,
        score: score,
        total: questionsData.length
    };
    
    tg.sendData(JSON.stringify(data));
}