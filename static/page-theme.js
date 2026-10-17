// Keep browser tint and exposed page edges in sync with session transitions.
(() => {
    const login = document.getElementById('login-page');
    const theme = document.getElementById('browser-theme');
    const syncTheme = () => {
        const atLogin = !login.classList.contains('hidden');
        document.documentElement.dataset.page = atLogin ? 'login' : 'chat';
        theme.content = atLogin ? '#050916' : '#ffffff';
    };
    syncTheme();
    new MutationObserver(syncTheme).observe(login, {
        attributes: true,
        attributeFilter: ['class'],
    });
})();
