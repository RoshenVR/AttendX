/**
 * Antigravity Particle Background
 * Features: Floating particles, depth effect, mouse parallax, theme colors
 */

const canvas = document.getElementById('bg-canvas');
const ctx = canvas.getContext('2d');

let width, height;
let particles = [];

// Theme Colors
const colors = [
    '#7b3fe4', // Purple
    '#2de2ff', // Cyan
    '#3a7cff', // Soft Blue
    '#10b981'  // Green
];

// Configuration
const config = {
    particleCount: 0, // Will be set based on screen size
    baseSize: 2,
    variation: 1.5,
    speed: 0.5,
    mouseRepelDist: 100,
    parallaxStrength: 0.05
};

// Resize Handling
function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;

    // Responsive particle count
    // Responsive particle count
    config.particleCount = Math.floor((width * height) / 5000);
    if (config.particleCount < 80) config.particleCount = 80;

    initParticles();
}

// Mouse State
const mouse = { x: -1000, y: -1000 };
window.addEventListener('mousemove', e => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
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
        this.speedY = -Math.random() * config.speed - 0.2; // Always float up slightly
        this.depth = Math.random() * 0.5 + 0.5; // 0.5 to 1.0
        this.opacity = Math.random() * 0.5 + 0.3;
    }

    update() {
        // Base movement
        this.x += this.speedX * this.depth;
        this.y += this.speedY * this.depth;

        // Mouse Parallax / Repel
        const dx = this.x - mouse.x;
        const dy = this.y - mouse.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < config.mouseRepelDist) {
            const force = (config.mouseRepelDist - dist) / config.mouseRepelDist;
            const angle = Math.atan2(dy, dx);
            this.x += Math.cos(angle) * force * 2;
            this.y += Math.sin(angle) * force * 2;
        }

        // Mouse Parallax (Standard drift opposite to mouse)
        // normalized mouse position -0.5 to 0.5
        const paraX = (mouse.x / width - 0.5) * config.parallaxStrength * this.depth;
        const paraY = (mouse.y / height - 0.5) * config.parallaxStrength * this.depth;

        this.x -= paraX;
        this.y -= paraY;

        // Wrap around
        if (this.y < -10) this.y = height + 10;
        if (this.x < -10) this.x = width + 10;
        if (this.x > width + 10) this.x = -10;
    }

    draw() {
        ctx.globalAlpha = this.opacity;
        ctx.fillStyle = this.color;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size * this.depth, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
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

    particles.forEach(p => {
        p.update();
        p.draw();
    });

    requestAnimationFrame(animate);
}

// Init
window.addEventListener('resize', resize);
resize();
animate();
