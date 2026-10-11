() => {
    const chips = document.querySelectorAll('.chip');
    const textarea = document.querySelector('#input-row textarea');

    chips.forEach(chip => {
        chip.addEventListener('click', () => {
            const text = chip.dataset.text;
            if (textarea && text) {
                textarea.value = text;
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                textarea.focus();
            }
        });
    });

    const inputRow = document.querySelector('#input-row');
    if (inputRow) {
        const ro = new MutationObserver(() => {
            const ta = inputRow.querySelector('textarea');
            if (!ta) return;
            ta.style.resize = 'none';
            ta.addEventListener('input', () => {
                ta.style.height = 'auto';
                ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
            });
            ro.disconnect();
        });
        ro.observe(inputRow, { childList: true, subtree: true });
    }

    const chatbot = document.querySelector('#chatbot .wrap');
    if (chatbot) {
        const mo = new MutationObserver(() => {
            chatbot.scrollTop = chatbot.scrollHeight;
            addTypingDots();
        });
        mo.observe(chatbot, { childList: true, subtree: true });
    }

    function addTypingDots() {
        const loadingBubbles = document.querySelectorAll('#chatbot .bubble.placeholder');
        loadingBubbles.forEach(bubble => {
            if (bubble.querySelector('.typing-dots')) return;
            bubble.classList.add('typing-bubble');
            bubble.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
        });
    }
}
