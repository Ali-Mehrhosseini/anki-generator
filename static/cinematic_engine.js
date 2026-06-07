/**
 * Cinematic Particle Physics Engine
 * High-performance 2D Canvas Engine for magical synthesis sequences.
 */

class CinematicEngine {
    constructor() {
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d', { alpha: true });
        this.particles = [];
        this.shockwaves = [];
        this.sparks = [];
        this.active = false;
        this.phase = 0; // 0: inactive, 1: gathering, 2: synthesis, 3: detonation
        this.targetWord = '';
        this.time = 0;
        this.glowIntensity = 0;
        this.detonationTime = 0;

        this.initDOM();
        this.handleResize = this.handleResize.bind(this);
        window.addEventListener('resize', this.handleResize);
        this.handleResize();
    }

    initDOM() {
        this.canvas.style.position = 'fixed';
        this.canvas.style.top = '0';
        this.canvas.style.left = '0';
        this.canvas.style.width = '100vw';
        this.canvas.style.height = '100vh';
        this.canvas.style.pointerEvents = 'none';
        this.canvas.style.zIndex = '999999';
        this.canvas.style.opacity = '0';
        this.canvas.style.transition = 'opacity 0.5s ease-in-out';
        document.body.appendChild(this.canvas);
    }

    handleResize() {
        this.width = window.innerWidth;
        this.height = window.innerHeight;
        this.canvas.width = this.width;
        this.canvas.height = this.height;
        this.centerX = this.width / 2;
        this.centerY = this.height / 2;
    }

    startSequence(word) {
        this.targetWord = word;
        this.active = true;
        this.phase = 1;
        this.time = 0;
        this.particles = [];
        this.shockwaves = [];
        this.sparks = [];
        this.glowIntensity = 0;
        this.canvas.style.opacity = '1';
        
        // Dim background
        document.body.style.transition = 'filter 1s ease-in-out';
        document.body.style.filter = 'brightness(0.2) contrast(1.2)';

        // Spawn initial particles
        for(let i=0; i<3000; i++) {
            this.spawnParticle(true);
        }

        requestAnimationFrame(this.render.bind(this));
        
        // Transition to synthesis
        setTimeout(() => {
            if (this.phase === 1) this.phase = 2;
        }, 1500);
    }

    detonate() {
        if (!this.active) return;
        this.phase = 3;
        this.detonationTime = 0;

        // Create massive shockwaves
        this.shockwaves.push({ r: 0, maxR: Math.max(this.width, this.height) * 1.5, speed: 40, thickness: 150, alpha: 1, color: '255, 255, 255' });
        this.shockwaves.push({ r: 0, maxR: Math.max(this.width, this.height) * 1.2, speed: 25, thickness: 80, alpha: 0.8, color: '66, 133, 244' });
        this.shockwaves.push({ r: 0, maxR: Math.max(this.width, this.height), speed: 15, thickness: 30, alpha: 0.6, color: '234, 67, 53' });

        // Explode particles outward
        for(let p of this.particles) {
            const angle = Math.atan2(p.y - this.centerY, p.x - this.centerX);
            const force = Math.random() * 80 + 30;
            p.vx = Math.cos(angle) * force;
            p.vy = Math.sin(angle) * force;
            p.life = Math.random() * 100 + 50;
            p.isExploding = true;
        }

        // Add extreme sparks
        for(let i=0; i<800; i++) {
            const angle = Math.random() * Math.PI * 2;
            const force = Math.random() * 120 + 20;
            this.sparks.push({
                x: this.centerX,
                y: this.centerY,
                vx: Math.cos(angle) * force,
                vy: Math.sin(angle) * force,
                life: Math.random() * 80 + 30,
                color: Math.random() > 0.5 ? '#fff' : '#4285f4',
                size: Math.random() * 6 + 1
            });
        }

        // Restore DOM
        document.body.style.filter = 'none';

        // End sequence
        setTimeout(() => {
            this.canvas.style.opacity = '0';
            setTimeout(() => {
                this.active = false;
                this.phase = 0;
                this.ctx.clearRect(0, 0, this.width, this.height);
            }, 500);
        }, 1500);
    }

    spawnParticle(distant = false) {
        const angle = Math.random() * Math.PI * 2;
        const radius = distant ? Math.max(this.width, this.height) : (Math.random() * 200 + 100);
        this.particles.push({
            x: this.centerX + Math.cos(angle) * radius,
            y: this.centerY + Math.sin(angle) * radius,
            vx: 0,
            vy: 0,
            size: Math.random() * 3 + 0.5,
            color: this.getRandomColor(),
            life: Math.random() * 100 + 100,
            angle: angle,
            radius: radius,
            speed: Math.random() * 0.08 + 0.02,
            isExploding: false
        });
    }

    getRandomColor() {
        const colors = ['#4285f4', '#34a853', '#fbbc04', '#ea4335', '#ffffff', '#a142f4', '#00e5ff', '#ff00ff'];
        return colors[Math.floor(Math.random() * colors.length)];
    }

    updatePhysics() {
        if (this.phase === 1 || this.phase === 2) {
            // Continually spawn to keep dense
            if (this.particles.length < 5000) {
                for(let i=0; i<80; i++) this.spawnParticle(true);
            }

            for (let i = this.particles.length - 1; i >= 0; i--) {
                let p = this.particles[i];
                p.angle += p.speed;
                // Spiral inward exponentially faster
                p.radius *= 0.93; 
                
                if (p.radius < 5) {
                    p.radius = Math.max(this.width, this.height) * (Math.random() * 0.5 + 0.5);
                    p.angle = Math.random() * Math.PI * 2;
                }

                // Add some chaotic noise
                const noiseX = Math.sin(this.time * 0.1 + p.y * 0.01) * 15;
                const noiseY = Math.cos(this.time * 0.1 + p.x * 0.01) * 15;

                p.x = this.centerX + Math.cos(p.angle) * p.radius + noiseX;
                p.y = this.centerY + Math.sin(p.angle) * p.radius + noiseY;
            }

            if (this.phase === 2) {
                this.glowIntensity = Math.min(this.glowIntensity + 0.03, 1);
            }
        } else if (this.phase === 3) {
            this.detonationTime++;
            
            for (let i = this.particles.length - 1; i >= 0; i--) {
                let p = this.particles[i];
                p.x += p.vx;
                p.y += p.vy;
                p.vx *= 0.94; // Friction
                p.vy *= 0.94;
                p.life--;
                if (p.life <= 0) this.particles.splice(i, 1);
            }

            for (let i = this.sparks.length - 1; i >= 0; i--) {
                let s = this.sparks[i];
                s.x += s.vx;
                s.y += s.vy;
                s.vx *= 0.88;
                s.vy *= 0.88;
                s.size *= 0.95;
                s.life--;
                if (s.life <= 0) this.sparks.splice(i, 1);
            }

            for (let i = this.shockwaves.length - 1; i >= 0; i--) {
                let sw = this.shockwaves[i];
                sw.r += sw.speed;
                sw.alpha *= 0.88;
                if (sw.alpha < 0.01) this.shockwaves.splice(i, 1);
            }
        }
    }

    render() {
        if (!this.active) return;

        this.time++;

        // Clear with fade for trail effect
        this.ctx.globalCompositeOperation = 'source-over';
        this.ctx.fillStyle = this.phase === 3 ? 'rgba(0,0,0,0.3)' : 'rgba(0,0,0,0.1)';
        this.ctx.fillRect(0, 0, this.width, this.height);

        this.ctx.globalCompositeOperation = 'lighter';

        this.updatePhysics();

        // Draw Shockwaves
        if (this.phase === 3) {
            for (let sw of this.shockwaves) {
                this.ctx.beginPath();
                this.ctx.arc(this.centerX, this.centerY, sw.r, 0, Math.PI * 2);
                this.ctx.lineWidth = sw.thickness * sw.alpha;
                this.ctx.strokeStyle = `rgba(${sw.color}, ${sw.alpha})`;
                this.ctx.stroke();
            }
        }

        // Draw Particles
        for (let p of this.particles) {
            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            this.ctx.fillStyle = p.color;
            let alpha = p.isExploding ? (p.life / 150) : (p.radius < 50 ? p.radius/50 : 1);
            this.ctx.globalAlpha = Math.max(0, Math.min(1, alpha));
            this.ctx.fill();
        }

        // Draw Sparks
        for (let s of this.sparks) {
            this.ctx.beginPath();
            this.ctx.moveTo(s.x, s.y);
            this.ctx.lineTo(s.x - s.vx * 2, s.y - s.vy * 2);
            this.ctx.strokeStyle = s.color;
            this.ctx.lineWidth = s.size;
            this.ctx.globalAlpha = Math.max(0, s.life / 80);
            this.ctx.stroke();
        }

        this.ctx.globalAlpha = 1;

        // Draw Singularity & Text
        if (this.phase === 1 || this.phase === 2) {
            // Black hole center
            this.ctx.globalCompositeOperation = 'source-over';
            this.ctx.beginPath();
            this.ctx.arc(this.centerX, this.centerY, 40 + Math.sin(this.time * 0.2) * 5, 0, Math.PI * 2);
            this.ctx.fillStyle = '#000';
            this.ctx.fill();
            this.ctx.shadowColor = '#4285f4';
            this.ctx.shadowBlur = 80 + Math.sin(this.time * 0.3) * 40;
            this.ctx.strokeStyle = '#fff';
            this.ctx.lineWidth = 3;
            this.ctx.stroke();
            this.ctx.shadowBlur = 0;

            if (this.phase === 2 && this.targetWord) {
                this.ctx.font = 'bold 90px "Outfit", sans-serif';
                this.ctx.textAlign = 'center';
                this.ctx.textBaseline = 'middle';
                
                // Pulsing glow
                const textGlow = 40 + Math.sin(this.time * 0.1) * 20;
                this.ctx.shadowColor = '#fff';
                this.ctx.shadowBlur = textGlow;
                
                const alpha = this.glowIntensity * (0.8 + Math.sin(this.time * 0.3) * 0.2);
                this.ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
                this.ctx.fillText(this.targetWord.toUpperCase(), this.centerX, this.centerY);
                this.ctx.shadowBlur = 0;
            }
        }

        if (this.active) {
            requestAnimationFrame(this.render.bind(this));
        }
    }
}

window.cinematicEngine = new CinematicEngine();
