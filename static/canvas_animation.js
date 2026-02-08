/**
 * Antigravity Particle Network Animation
 * 
 * Features:
 * - Subtle floating nodes
 * - Local connection only
 * - Mouse repulsion (Anti-gravity effect)
 * - Mobile gyro support with iOS permission handling
 */

const canvas = document.getElementById('bg-animation');
const ctx = canvas.getContext('2d');

let width, height;
let particles = [];

// Configuration
const config = {
    particleCount: 0,
    particleColor1: '#4A3AFF',
    particleColor2: '#8E8FFA',
    lineColor: 'rgba(74, 58, 255, 0.2)', // Reduced opacity
    particleRadius: 2.5,
    speed: 0.5,
    connectionDistance: 150,
    mouseRepelDistance: 120, // Reverted to repulsion distance
    mouseRepelForce: 2,      // Reverted force
    gyroSensitivity: 0.15     // Good balance
};

// Mouse state
const mouse = {
    x: null,
    y: null
};

// Gyro state
const gyro = {
    x: 0,
    y: 0
};

class Particle {
    constructor() {
        this.x = Math.random() * width;
        this.y = Math.random() * height;
        this.vx = (Math.random() - 0.5) * config.speed;
        this.vy = (Math.random() - 0.5) * config.speed;
        this.color = Math.random() > 0.5 ? config.particleColor1 : config.particleColor2;
        this.opacity = Math.random() * 0.4 + 0.3; // 0.3 to 0.7 (Subtler)
        this.radius = Math.random() * 2 + 1;
    }

    update() {
        // Base movement
        this.x += this.vx + gyro.x;
        this.y += this.vy + gyro.y;

        // Mouse Repulsion (The "Anti-gravity" effect)
        if (mouse.x != null) {
            const dx = this.x - mouse.x;
            const dy = this.y - mouse.y;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (distance < config.mouseRepelDistance) {
                const forceDirectionX = dx / distance;
                const forceDirectionY = dy / distance;
                const force = (config.mouseRepelDistance - distance) / config.mouseRepelDistance;
                // Move away from mouse
                const directionX = forceDirectionX * force * config.mouseRepelForce;
                const directionY = forceDirectionY * force * config.mouseRepelForce;

                this.x += directionX;
                this.y += directionY;
            }
        }

        // Boundary Check (bounce)
        if (this.x < 0 || this.x > width) this.vx = -this.vx;
        if (this.y < 0 || this.y > height) this.vy = -this.vy;
    }

    draw() {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
        ctx.globalAlpha = this.opacity;
        ctx.fillStyle = this.color;
        ctx.fill();
        ctx.globalAlpha = 1;
    }
}

function init() {
    resize();
    createParticles();
    animate();

    // Check for HTTPS/Secure Context which is required for Gyro
    if (location.protocol !== 'https:' && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
        console.warn("Gyroscope requires HTTPS or localhost. Current protocol: " + location.protocol);
    }
}

function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
    const area = width * height;
    config.particleCount = Math.floor(area / 9000);
}

function createParticles() {
    particles = [];
    for (let i = 0; i < config.particleCount; i++) {
        particles.push(new Particle());
    }
}

function animate() {
    ctx.clearRect(0, 0, width, height);

    for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.update();
        p.draw();

        // Connect to nearby particles (local only)
        for (let j = i; j < particles.length; j++) {
            const p2 = particles[j];
            const dx = p.x - p2.x;
            const dy = p.y - p2.y;
            const distance = dx * dx + dy * dy;

            if (distance < (config.connectionDistance * config.connectionDistance)) {
                const opacityValue = 1 - (distance / (config.connectionDistance * config.connectionDistance));
                ctx.strokeStyle = config.lineColor;
                ctx.globalAlpha = opacityValue * 0.5; // reduced line alpha
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(p.x, p.y);
                ctx.lineTo(p2.x, p2.y);
                ctx.stroke();
                ctx.globalAlpha = 1;
            }
        }
    }

    requestAnimationFrame(animate);
}

// Event Listeners
window.addEventListener('resize', () => {
    resize();
    createParticles();
});

window.addEventListener('mousemove', (e) => {
    mouse.x = e.x;
    mouse.y = e.y;
});

window.addEventListener('mouseout', () => {
    mouse.x = null;
    mouse.y = null;
});

// Mobile Gyro Support
function handleOrientation(event) {
    let x = event.gamma;
    let y = event.beta;

    if (x === null || y === null) return;

    if (x > 90) x = 90;
    if (x < -90) x = -90;

    gyro.x = (x / 90) * config.gyroSensitivity;
    gyro.y = (y / 180) * config.gyroSensitivity;
}

// Permission UI
function createPermissionButton() {
    // Only show if we suspect we need permission (iOS/Mobile)
    // and if we haven't already got it.
    if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
        const btn = document.createElement('button');
        btn.innerText = "Enable Gyro Animation";
        btn.style.position = 'fixed';
        btn.style.bottom = '20px';
        btn.style.right = '20px';
        btn.style.zIndex = '10000';
        btn.style.padding = '10px 15px';
        btn.style.background = '#4A3AFF';
        btn.style.color = 'white';
        btn.style.border = 'none';
        btn.style.borderRadius = '20px';
        btn.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        btn.style.cursor = 'pointer';

        btn.onclick = async () => {
            try {
                const permissionState = await DeviceOrientationEvent.requestPermission();
                if (permissionState === 'granted') {
                    window.addEventListener('deviceorientation', handleOrientation);
                    btn.remove(); // Hide button after granting
                } else {
                    alert('Permission denied. Gyro animation disabled.');
                    btn.remove();
                }
            } catch (e) {
                console.error(e);
            }
        };
        document.body.appendChild(btn);
    } else {
        // Non-iOS or older devices: try adding immediately
        window.addEventListener('deviceorientation', handleOrientation);
    }
}

// Init permission button on load
// We use a small timeout to ensure DOM is ready and not block other scripts
setTimeout(createPermissionButton, 1000);

init();
