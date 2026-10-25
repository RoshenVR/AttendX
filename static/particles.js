/**
 * AttendX Floating Particles Background Animation
 * Features: Floating multi-colored particles, depth effect, mouse parallax and repulsion
 */

(function() {
    function initCanvasAnimation() {
        const canvas = document.getElementById('bg-canvas');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        let width, height;
        let particles = [];

        // AttendX Brand Theme Colors
        const colors = [
            '#7c3aed', // Purple
            '#06b6d4', // Cyan
            '#2563eb', // Electric Blue
            '#10b981', // Emerald Green
            '#f43f5e'  // Coral Rose
        ];

        // Configuration
        const config = {
            particleCount: 0,
            baseSize: 2.2,
            variation: 2.2,
            speed: 0.45,
            mouseRepelDist: 120,
            parallaxStrength: 0.05
        };

        function resize() {
            width = canvas.width = window.innerWidth;
            height = canvas.height = window.innerHeight;

            // Responsive particle count based on display area
            config.particleCount = Math.floor((width * height) / 7500);
            if (config.particleCount < 70) config.particleCount = 70;
            if (config.particleCount > 160) config.particleCount = 160;

            initParticles();
        }

        // Mouse State
        const mouse = { x: -1000, y: -1000 };
        window.addEventListener('mousemove', function(e) {
            mouse.x = e.clientX;
            mouse.y = e.clientY;
        });

        window.addEventListener('mouseleave', function() {
            mouse.x = -1000;
            mouse.y = -1000;
        });

        class Particle {
            constructor() {
                this.reset(true);
            }

            reset(randomY = false) {
                this.x = Math.random() * width;
                this.y = randomY ? Math.random() * height : height + 10;
                this.size = Math.random() * config.variation + config.baseSize;
                this.color = colors[Math.floor(Math.random() * colors.length)];
                this.speedX = (Math.random() - 0.5) * config.speed;
                this.speedY = -Math.random() * config.speed - 0.25; // Gentle float upwards
                this.depth = Math.random() * 0.6 + 0.4; // 0.4 to 1.0 depth scale
                this.opacity = Math.random() * 0.45 + 0.4; // 0.40 to 0.85 opacity for clear visibility
            }

            update() {
                // Base movement
                this.x += this.speedX * this.depth;
                this.y += this.speedY * this.depth;

                // Mouse Repulsion (Interactive Anti-gravity effect)
                const dx = this.x - mouse.x;
                const dy = this.y - mouse.y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < config.mouseRepelDist) {
                    const force = (config.mouseRepelDist - dist) / config.mouseRepelDist;
                    const angle = Math.atan2(dy, dx);
                    this.x += Math.cos(angle) * force * 2.8;
                    this.y += Math.sin(angle) * force * 2.8;
                }

                // Mouse Parallax drift
                const paraX = (mouse.x / width - 0.5) * config.parallaxStrength * this.depth;
                const paraY = (mouse.y / height - 0.5) * config.parallaxStrength * this.depth;

                this.x -= paraX;
                this.y -= paraY;

                // Wrap around edges
                if (this.y < -15) this.y = height + 15;
                if (this.x < -15) this.x = width + 15;
                if (this.x > width + 15) this.x = -15;
            }

            draw() {
                ctx.save();
                ctx.globalAlpha = this.opacity;
                ctx.fillStyle = this.color;
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.size * this.depth, 0, Math.PI * 2);
                ctx.fill();
                ctx.restore();
            }
        }

        function initParticles() {
            particles = [];
            for (let i = 0; i < config.particleCount; i++) {
                particles.push(new Particle());
            }
        }

        function animate() {
            ctx.clearRect(0, 0, width, height);

            for (let i = 0; i < particles.length; i++) {
                particles[i].update();
                particles[i].draw();
            }

            requestAnimationFrame(animate);
        }

        window.addEventListener('resize', resize);
        resize();
        animate();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCanvasAnimation);
    } else {
        initCanvasAnimation();
    }
})();
