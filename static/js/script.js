// Main JavaScript file for Afreen Fashion

document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle (if needed)
    const mobileMenuToggle = document.querySelector('.mobile-menu-toggle');
    const navMenu = document.querySelector('nav ul');
    
    if (mobileMenuToggle && navMenu) {
        mobileMenuToggle.addEventListener('click', function() {
            navMenu.classList.toggle('active');
        });
    }
    
    // Quantity input controls
    document.querySelectorAll('.quantity-control').forEach(control => {
        const input = control.querySelector('input');
        const minusBtn = control.querySelector('.minus');
        const plusBtn = control.querySelector('.plus');
        
        minusBtn.addEventListener('click', () => {
            if (parseInt(input.value) > 1) {
                input.value = parseInt(input.value) - 1;
            }
        });
        
        plusBtn.addEventListener('click', () => {
            input.value = parseInt(input.value) + 1;
        });
    });
    
    // Form validation
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function(e) {
            let valid = true;
            const inputs = this.querySelectorAll('input[required], select[required], textarea[required]');
            
            inputs.forEach(input => {
                if (!input.value.trim()) {
                    input.classList.add('error');
                    valid = false;
                } else {
                    input.classList.remove('error');
                }
            });
            
            if (!valid) {
                e.preventDefault();
                alert('Please fill in all required fields.');
            }
        });
    });
    
    // Image preview for file inputs
    document.querySelectorAll('input[type="file"]').forEach(input => {
        if (input.accept.includes('image')) {
            input.addEventListener('change', function() {
                const preview = this.nextElementSibling;
                if (this.files && this.files[0]) {
                    const reader = new FileReader();
                    
                    reader.onload = function(e) {
                        if (preview && preview.tagName === 'IMG') {
                            preview.src = e.target.result;
                        } else {
                            const img = document.createElement('img');
                            img.src = e.target.result;
                            img.className = 'product-thumb';
                            input.parentNode.insertBefore(img, preview);
                        }
                    }
                    
                    reader.readAsDataURL(this.files[0]);
                }
            });
        }
    });
    
    // Search functionality
    const searchForm = document.querySelector('.search-form');
    if (searchForm) {
        searchForm.addEventListener('submit', function(e) {
            const searchInput = this.querySelector('input[name="search"]');
            if (!searchInput.value.trim()) {
                e.preventDefault();
            }
        });
    }

    // Mobile menu toggle
    document.querySelector('.menu-toggle').addEventListener('click', function() {
        const nav = document.querySelector('nav ul');
        nav.classList.toggle('active');
    
        // Toggle hamburger/close icon
        if (nav.classList.contains('active')) {
            this.innerHTML = '<i class="fas fa-times"></i>';
        } else {
            this.innerHTML = '<i class="fas fa-bars"></i>';
        }
    });

    // Scroll animation reveal
    function revealOnScroll() {
        const elements = document.querySelectorAll('.reveal');
        elements.forEach(el => {
            const elementTop = el.getBoundingClientRect().top;
            const windowHeight = window.innerHeight;
            if (elementTop < windowHeight - 50) {
                el.classList.add('active');
            }
        });
    }

    window.addEventListener('scroll', revealOnScroll);
    revealOnScroll(); // Initialize
    
    // Cart item quantity update
    document.querySelectorAll('.update-form').forEach(form => {
        form.addEventListener('submit', function(e) {
            const quantityInput = this.querySelector('input[name="quantity"]');
            if (parseInt(quantityInput.value) < 1) {
                e.preventDefault();
                alert('Quantity must be at least 1');
            }
        });
    });
});