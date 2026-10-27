import { useMemo, useRef } from 'react';
import { Canvas, useFrame, type ThreeEvent } from '@react-three/fiber';
import * as THREE from 'three';

// "Your area, seen from above": an imaginary city drawn in holographic
// particles, houses and apartment buildings along streets. Above each one
// floats a point in the colour of its DPE. Under the cursor (or finger) the
// buildings light up and rise, and the F and G points flare. Illustration
// only: the city and its labels are random.

const COLORS = ['#009C6D', '#52B153', '#78BD76', '#F4E70F', '#F0B40F', '#EB8235', '#D7221F'];
// Rough share of each class in the housing stock, for the look of the city
const SHARE = [0.02, 0.04, 0.12, 0.31, 0.27, 0.15, 0.09];

const VERTEX = /* glsl */ `
uniform float uTime; uniform vec2 uMouse; uniform float uPower; uniform float uPixel;
attribute vec2 aCenter; attribute float aKind; attribute vec3 aColor; attribute float aPassoire; attribute float aSeed;
varying vec3 vColor; varying float vAlpha; varying float vKind;
void main(){
  vec3 p=position;
  float lens=(1.-smoothstep(0.,2.4,distance(aCenter,uMouse)))*uPower;
  float size;
  if(aKind<.5){                       // building outline
    p.y*=1.+lens*.35;
    float tw=.75+.25*sin(uTime*2.+aSeed*40.);
    vColor=mix(vec3(.22,.5,1.),vec3(.55,.85,1.),lens)+aColor*aPassoire*lens*.6;
    vAlpha=(.32+lens*.8)*tw;
    size=1.+lens*.7;
  } else if(aKind<1.5){               // DPE point above the roof
    p.y=p.y*(1.+lens*.35)+lens*.25+sin(uTime*1.6+aSeed*6.28)*.03;
    float pulse=aPassoire*(.5+.5*sin(uTime*3.+aSeed*20.));
    vColor=aColor;
    vAlpha=.75+lens*.25;
    size=2.6+aPassoire*(1.+pulse*1.2)*(.4+lens*1.6)+lens*2.2;
  } else {                            // streets
    vColor=vec3(.2,.45,.95);
    vAlpha=.18+lens*.25;
    size=.9;
  }
  vKind=aKind;
  vec4 mv=modelViewMatrix*vec4(p,1.);
  gl_PointSize=uPixel*size*(18./-mv.z);
  gl_Position=projectionMatrix*mv;
}`;

const FRAGMENT = /* glsl */ `
varying vec3 vColor; varying float vAlpha; varying float vKind;
void main(){
  float d=length(gl_PointCoord-.5);
  float core=1.-smoothstep(.2,.5,d);
  float halo=(1.-smoothstep(0.,.5,d))*step(.5,vKind)*step(vKind,1.5)*.6;
  float a=(core+halo)*vAlpha;
  if(a<.01) discard;
  gl_FragColor=vec4(vColor*(1.+halo),a);
}`;

/** Small seeded random generator: the same city on every visit. */
function rng(seed: number) {
    return () => {
        seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
        let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

function buildCity(blocksX: number, blocksZ: number, step: number) {
    const rand = rng(7);
    const pos: number[] = [], center: number[] = [], kind: number[] = [], color: number[] = [], passoire: number[] = [], seed: number[] = [];
    const c = new THREE.Color();
    const push = (x: number, y: number, z: number, cx: number, cz: number, k: number, col: THREE.Color, pass: number, s: number) => {
        pos.push(x, y, z); center.push(cx, cz); kind.push(k); color.push(col.r, col.g, col.b); passoire.push(pass); seed.push(s);
    };
    const line = (a: number[], b: number[], cx: number, cz: number, col: THREE.Color, pass: number, s: number, k = 0, spacing = step) => {
        const len = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
        const n = Math.max(1, Math.round(len / spacing));
        for (let i = 0; i <= n; i++) {
            const t = i / n;
            push(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, cx, cz, k, col, pass, s + i * 0.013);
        }
    };
    const LOT = 0.9, STREET = 0.6, LX = 3, LZ = 2;
    const pitchX = LX * LOT + STREET, pitchZ = LZ * LOT + STREET;
    const maxR = Math.hypot(blocksX * pitchX, blocksZ * pitchZ);
    for (let bx = -blocksX; bx <= blocksX; bx++) for (let bz = -blocksZ; bz <= blocksZ; bz++) {
        const ox = bx * pitchX - (LX * LOT) / 2, oz = bz * pitchZ - (LZ * LOT) / 2;
        for (let lx = 0; lx < LX; lx++) for (let lz = 0; lz < LZ; lz++) {
            const cx = ox + (lx + 0.5) * LOT, cz = oz + (lz + 0.5) * LOT;
            const centrality = 1 - Math.min(Math.hypot(cx, cz) / maxR, 1);
            if (rand() < 0.08) continue; // empty lot
            // DPE class of the lot
            let r = rand(), cls = 0;
            while (cls < 6 && r > SHARE[cls]) { r -= SHARE[cls]; cls++; }
            c.set(COLORS[cls]);
            const pass = cls >= 5 ? 1 : 0, s = rand();
            const building = rand() < 0.15 + centrality * 0.75;
            const w = building ? 0.55 + rand() * 0.2 : 0.45 + rand() * 0.15;
            const d = building ? 0.55 + rand() * 0.2 : 0.38 + rand() * 0.12;
            const h = building ? 0.7 + rand() * (0.6 + centrality * 2.6) : 0.28 + rand() * 0.1;
            const x0 = cx - w / 2, x1 = cx + w / 2, z0 = cz - d / 2, z1 = cz + d / 2;
            const corners = [[x0, z0], [x1, z0], [x1, z1], [x0, z1]];
            // Outline: vertical edges, base and top rectangles
            for (const [x, z] of corners) line([x, 0, z], [x, h, z], cx, cz, c, pass, s);
            for (const y of [0, h]) for (let i = 0; i < 4; i++) {
                const [ax, az] = corners[i], [qx, qz] = corners[(i + 1) % 4];
                line([ax, y, az], [qx, y, qz], cx, cz, c, pass, s);
            }
            let top = h;
            if (building) {
                // Floors: a sparser ring every storey
                for (let y = 0.32; y < h - 0.1; y += 0.32) for (let i = 0; i < 4; i++) {
                    const [ax, az] = corners[i], [qx, qz] = corners[(i + 1) % 4];
                    line([ax, y, az], [qx, y, qz], cx, cz, c, pass, s, 0, step * 1.8);
                }
            } else {
                // Gable roof
                const ridge = h + 0.22;
                line([x0, ridge, cz], [x1, ridge, cz], cx, cz, c, pass, s);
                for (const x of [x0, x1]) { line([x, h, z0], [x, ridge, cz], cx, cz, c, pass, s); line([x, h, z1], [x, ridge, cz], cx, cz, c, pass, s); }
                top = ridge;
            }
            push(cx, top + 0.28, cz, cx, cz, 1, c, pass, s);
        }
    }
    // Streets: dotted centre lines between the blocks
    const none = new THREE.Color(0, 0, 0);
    const spanX = (blocksX + 0.5) * pitchX, spanZ = (blocksZ + 0.5) * pitchZ;
    for (let bx = -blocksX; bx <= blocksX + 1; bx++) {
        const x = (bx - 0.5) * pitchX;
        for (let z = -spanZ; z <= spanZ; z += 0.22) push(x, 0, z, x, z, 2, none, 0, 0);
    }
    for (let bz = -blocksZ; bz <= blocksZ + 1; bz++) {
        const z = (bz - 0.5) * pitchZ;
        for (let x = -spanX; x <= spanX; x += 0.22) push(x, 0, z, x, z, 2, none, 0, 0);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('aCenter', new THREE.Float32BufferAttribute(center, 2));
    g.setAttribute('aKind', new THREE.Float32BufferAttribute(kind, 1));
    g.setAttribute('aColor', new THREE.Float32BufferAttribute(color, 3));
    g.setAttribute('aPassoire', new THREE.Float32BufferAttribute(passoire, 1));
    g.setAttribute('aSeed', new THREE.Float32BufferAttribute(seed, 1));
    return { geometry: g, width: spanX * 2, depth: spanZ * 2 };
}

function Scene({ lite }: { lite: boolean }) {
    const group = useRef<THREE.Group>(null);
    const target = useRef(new THREE.Vector2(99, 99));
    const active = useRef(0);
    const city = useMemo(() => buildCity(lite ? 2 : 3, lite ? 2 : 2, lite ? 0.085 : 0.06), [lite]);
    const uniforms = useMemo(() => ({
        uTime: { value: 0 }, uMouse: { value: new THREE.Vector2(99, 99) }, uPower: { value: 0 },
        uPixel: { value: Math.max(Math.min(window.devicePixelRatio, 2), 1.25) * 1.6 },
    }), []);
    useFrame((state, dt) => {
        uniforms.uTime.value += dt;
        const t = state.clock.elapsedTime;
        // Without a pointer, the light wanders through the streets on its own
        const idle = active.current <= 0;
        const goal = idle ? new THREE.Vector2(Math.sin(t * 0.3) * city.width * 0.3, Math.cos(t * 0.23) * city.depth * 0.25) : target.current;
        uniforms.uMouse.value.lerp(goal, idle ? 0.025 : 0.14);
        uniforms.uPower.value = THREE.MathUtils.lerp(uniforms.uPower.value, idle ? 0.75 : 1, 0.05);
        active.current -= dt;
        if (group.current) group.current.rotation.y += dt * 0.025;
    });
    const onMove = (e: ThreeEvent<PointerEvent>) => {
        // Pointer in the city's own coordinates (the city turns slowly)
        const local = group.current!.worldToLocal(e.point.clone());
        target.current.set(local.x, local.z);
        active.current = 2;
    };
    return (
        <group ref={group}>
            <points geometry={city.geometry}>
                <shaderMaterial vertexShader={VERTEX} fragmentShader={FRAGMENT} uniforms={uniforms}
                    transparent depthWrite={false} blending={THREE.AdditiveBlending} />
            </points>
            {/* Invisible ground catching the pointer */}
            <mesh rotation={[-Math.PI / 2, 0, 0]} onPointerMove={onMove} visible={false}>
                <planeGeometry args={[city.width * 1.4, city.depth * 1.6]} />
                <meshBasicMaterial />
            </mesh>
        </group>
    );
}

export default function City({ active, lite }: { active: boolean; lite: boolean }) {
    return (
        <Canvas
            frameloop={active ? 'always' : 'never'}
            dpr={lite ? [1, 1.25] : [1, 1.75]}
            camera={{ position: lite ? [0, 15, 11] : [0, 14, 10.5], fov: 40 }}
            onCreated={({ camera }) => camera.lookAt(0, 0, 0.6)}
            gl={{ antialias: false, alpha: true, powerPreference: 'high-performance' }}
        >
            <Scene lite={lite} />
        </Canvas>
    );
}
