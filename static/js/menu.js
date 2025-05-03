    // Setup menu functionality
    function setupMenu() {
        const menuToggle = document.querySelector('.menu-toggle');
        const menu = document.querySelector('.menu');
        const menuOverlay = document.querySelector('.menu-overlay');
        const menuItems = document.querySelectorAll('.menu-item');

        // Toggle menu
        menuToggle.addEventListener('click', () => {
            menu.classList.toggle('visible');
            menuOverlay.classList.toggle('visible');
        });

        // Close menu when clicking overlay
        menuOverlay.addEventListener('click', () => {
            menu.classList.remove('visible');
            menuOverlay.classList.remove('visible');
        });

        // Menu item hover effects and click handling
        menuItems.forEach(item => {
            item.addEventListener('mouseenter', () => {
                item.style.transform = 'translateX(4px)';
            });

            item.addEventListener('mouseleave', () => {
                item.style.transform = 'translateX(0)';
            });

            // Handle clicks on menu items
            item.addEventListener('click', (e) => {
                const link = item.getAttribute('href');
                if (link) {
                    const currentPath = window.location.pathname;
                    if (link === currentPath) {
                        // If we're already on this page, prevent default and just close the menu
                        e.preventDefault();
                        menu.classList.remove('visible');
                        menuOverlay.classList.remove('visible');
                    }
                }
            });
        });

        // Close menu when pressing Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && menu.classList.contains('visible')) {
                menu.classList.remove('visible');
                menuOverlay.classList.remove('visible');
            }
        });
}
setupMenu();