const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios');

const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        executablePath: 'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
        headless: true
    }
});

client.on('qr', (qr) => {
    // Ini yang akan memunculkan QR Code di terminalmu
    qrcode.generate(qr, { small: true });
    console.log('QR Code sudah siap, silakan scan!');
});

client.on('ready', () => {
    console.log('Bot WhatsApp sudah online!');
});

client.on('message', async (msg) => {
    if (msg.fromMe) return;

    try {
        console.log('Pesan masuk:', msg.body);
        // Mengirim pesan ke backend FastAPI kita
        const response = await axios.post('http://127.0.0.1:8000/tanya', {
            pertanyaan: msg.body
        });

        // Membalas pesan
        msg.reply(response.data.jawaban);
    } catch (error) {
        console.error('Error:', error);
        msg.reply("Maaf, sistem sedang sibuk.");
    }
});

client.initialize();