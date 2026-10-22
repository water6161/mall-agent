() => {
    function setupInputAutoGrow() {
        const ro = new MutationObserver(() => {
            const inputArea = document.querySelector('#input-area');
            if (!inputArea) return;
            const ta = inputArea.querySelector('textarea');
            if (!ta) return;

            ta.style.resize = 'none';
            ta.style.overflow = 'hidden';

            ta.addEventListener('input', () => {
                ta.style.height = 'auto';
                ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
            });

            ro.disconnect();
        });
        ro.observe(document.body, { childList: true, subtree: true });
    }

    function setupWelcomeExamples() {
        document.addEventListener('click', (e) => {
            const ex = e.target.closest('.welcome-example');
            if (!ex) return;
            const text = ex.dataset.text;
            if (!text) return;
            const ta = document.querySelector('#input-area textarea');
            if (ta) {
                ta.value = text;
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.focus();
                setTimeout(() => {
                    const sendBtn = document.querySelector('#send-btn');
                    if (sendBtn) sendBtn.click();
                }, 100);
            }
        });
    }

    function setupSidebarNewChat() {
        document.addEventListener('click', (e) => {
            if (e.target.closest('#sidebar-new-chat')) {
                const clearBtn = document.querySelector('#clear-btn, .gr-button[class*="clear"]');
                const chatbotWrap = document.querySelector('#chatbot .wrap');
                if (chatbotWrap) {
                    const chat = chatbotWrap.closest('#chatbot');
                    if (chat && chat.querySelectorAll('.message').length === 0) {
                        const welcome = document.querySelector('#welcome-screen');
                        if (welcome) welcome.style.display = 'flex';
                    }
                }
                const clearButtons = document.querySelectorAll('button');
                clearButtons.forEach(btn => {
                    if (btn.textContent.includes('新对话') || btn.textContent.includes('Clear')) {
                        btn.click();
                    }
                });
            }
        });
    }

    function setupHistoryItemClick() {
        document.addEventListener('click', (e) => {
            const item = e.target.closest('.history-item');
            if (!item) return;
            const sid = item.dataset.sid;
            if (!sid) return;
            const sel = document.querySelector('#session-dropdown select, #session-dropdown [data-slot="select"]');
            if (sel) {
                const nativeSelect = sel.querySelector('select') || sel;
                if (nativeSelect instanceof HTMLSelectElement) {
                    nativeSelect.value = sid;
                    nativeSelect.dispatchEvent(new Event('change', { bubbles: true }));
                }
                const loadBtn = document.querySelector('#load-btn, button');
            }
            const loadBtns = document.querySelectorAll('#sidebar-history-btns button, button');
            loadBtns.forEach(btn => {
                if (btn.textContent.includes('载入') || btn.textContent.includes('Load')) {
                    btn.click();
                }
            });
        });
    }

    function setupWelcomeVisibility() {
        const ro = new MutationObserver(() => {
            const welcome = document.querySelector('#welcome-screen');
            const chatWrap = document.querySelector('#chatbot .wrap');
            if (!welcome || !chatWrap) return;

            const hasMessages = chatWrap.querySelectorAll('.message').length > 0;
            if (hasMessages) {
                welcome.style.display = 'none';
            } else {
                welcome.style.display = 'flex';
            }
        });

        function observeChatbot() {
            const cb = document.querySelector('#chatbot .wrap');
            if (cb) {
                ro.observe(cb, { childList: true, subtree: true });
            }
        }
        observeChatbot();

        const bodyRo = new MutationObserver(observeChatbot);
        bodyRo.observe(document.body, { childList: true, subtree: true });
    }

    function setupAutoScroll() {
        const mo = new MutationObserver(() => {
            const chatWrap = document.querySelector('#chatbot .wrap');
            if (chatWrap) {
                chatWrap.scrollTop = chatWrap.scrollHeight;
                addTypingDots();
            }
        });

        function observeChat() {
            const wrap = document.querySelector('#chatbot .wrap');
            if (wrap) {
                mo.observe(wrap, { childList: true, subtree: true });
            }
        }
        observeChat();

        const bodyMo = new MutationObserver(observeChat);
        bodyMo.observe(document.body, { childList: true, subtree: true });
    }

    function addTypingDots() {
        const loadingBubbles = document.querySelectorAll('#chatbot .bubble.placeholder');
        loadingBubbles.forEach(bubble => {
            if (bubble.querySelector('.typing-dots')) return;
            bubble.classList.add('typing-bubble');
            bubble.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
        });
    }

    function setupWelcomeTabs() {
        document.addEventListener('click', (e) => {
            const tab = e.target.closest('.welcome-tab');
            if (!tab) return;
            document.querySelectorAll('.welcome-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
        });
    }

    function setupSidebarToggle() {
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('#sidebar-toggle');
            if (!btn) return;
            const sb = document.querySelector('#sidebar');
            if (!sb) return;
            sb.classList.toggle('collapsed');
            btn.classList.toggle('collapsed');
        });
    }

    setupInputAutoGrow();
    setupWelcomeExamples();
    setupSidebarNewChat();
    setupHistoryItemClick();
    setupWelcomeVisibility();
    setupAutoScroll();
    setupWelcomeTabs();
    setupSidebarToggle();
}
