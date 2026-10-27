import { useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

// Hero scene: a holographic house, glowing blue edges over translucent faces,
// tiled roofs and a grid floor. It draws itself from the ground up on load,
// then a scan line sweeps it regularly; it turns towards the cursor. Loaded
// lazily after the page text, renders only while on screen.

// Heights in world units: the ground is at y = 0, the roof tops at about 2
const START = -0.05;
const END = 2.2;
const BUILD = 2.6;    // seconds to draw the house on load
const SWEEP = 5;      // seconds between two scan sweeps

const VERTEX = /* glsl */ `
varying vec3 vWorld; varying vec3 vNormal;
void main(){
  vec4 w=modelMatrix*vec4(position,1.);
  vWorld=w.xyz; vNormal=normalize(mat3(modelMatrix)*normal);
  gl_Position=projectionMatrix*viewMatrix*w;
}`;

// Shared by faces and lines: drawn below the build height, brighter on the scan band.
// Heights are relative to the group (the house stands on y = uGround in world space).
const COMMON = /* glsl */ `
uniform float uBuild; uniform float uSweep; uniform float uTime; uniform float uGround;
float built(float y){ return 1.-smoothstep(uBuild-.03,uBuild+.03,y); }
float band(float y, float h){ return (1.-smoothstep(0.,.05,abs(y-h)))+(1.-smoothstep(0.,.35,abs(y-h)))*.3; }`;

const FACE_FRAGMENT = /* glsl */ `
${COMMON}
uniform vec3 uColor; uniform float uOpacity;
varying vec3 vWorld; varying vec3 vNormal;
void main(){
  float y=vWorld.y-uGround;
  float fres=pow(1.-abs(dot(normalize(vNormal),normalize(cameraPosition-vWorld))),2.);
  float lines=.85+.15*sin(y*140.-uTime*6.);          // hologram scanlines
  float a=(uOpacity+fres*.3)*lines*built(y);
  a+=band(y,uSweep)*.16+band(y,uBuild)*.45*(1.-step(${END.toFixed(2)},uBuild));
  gl_FragColor=vec4(uColor*(1.+fres),a);
}`;

const LINE_FRAGMENT = /* glsl */ `
${COMMON}
uniform vec3 uColor; uniform float uOpacity;
varying vec3 vWorld; varying vec3 vNormal;
void main(){
  float y=vWorld.y-uGround;
  float a=uOpacity*(.12+.88*built(y));
  vec3 col=uColor+vec3(.6,.8,1.)*band(y,uSweep)*.9;
  gl_FragColor=vec4(col,a);
}`;

const FLOOR_FRAGMENT = /* glsl */ `
uniform float uTime;
varying vec2 vUv;
void main(){
  vec2 p=(vUv-.5)*7.;
  vec2 g=abs(fract(p*4.)-.5);
  float line=1.-smoothstep(0.,.05,min(g.x,g.y));
  vec2 G=abs(fract(p)-.5);
  float major=1.-smoothstep(0.,.025,min(G.x,G.y));
  float fade=1.-smoothstep(1.4,3.4,length(p));
  float pulse=.7+.3*sin(length(p)*3.-uTime*1.5);
  gl_FragColor=vec4(vec3(.25,.6,1.),(line*.28+major*.5)*fade*pulse);
}`;

const pointer = { x: 0, y: 0 };

/** Gable roof: triangle in XY (base width, height), extruded along Z over depth, centred. */
function gable(width: number, height: number, depth: number) {
    const s = new THREE.Shape();
    s.moveTo(-width / 2, 0); s.lineTo(width / 2, 0); s.lineTo(0, height); s.closePath();
    const g = new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: false });
    g.translate(0, 0, -depth / 2);
    return g;
}

function lineGeometry(pts: number[]) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    return g;
}

/** Tile grid on both slopes of a gable(width, height, depth) roof. */
function tiles(width: number, height: number, depth: number, rows: number, cols: number) {
    const pts: number[] = [];
    for (const side of [-1, 1]) {
        const eave = new THREE.Vector3(side * width / 2, 0, 0), ridge = new THREE.Vector3(0, height, 0);
        const lift = new THREE.Vector3(side * height, width / 2, 0).normalize().multiplyScalar(0.004);
        for (let r = 1; r < rows; r++) { // parallel to the ridge
            const p = eave.clone().lerp(ridge, r / rows).add(lift);
            pts.push(p.x, p.y, -depth / 2, p.x, p.y, depth / 2);
        }
        for (let c = 1; c < cols; c++) { // down the slope
            const z = -depth / 2 + (depth * c) / cols;
            const a = eave.clone().add(lift), b = ridge.clone().add(lift);
            pts.push(a.x, a.y, z, b.x, b.y, z);
        }
    }
    return lineGeometry(pts);
}

/** Window frame with mullions, in the XY plane. */
function windowLines(w: number, h: number, cols: number, rows: number) {
    const p: number[] = [];
    const seg = (x1: number, y1: number, x2: number, y2: number) => p.push(x1, y1, 0, x2, y2, 0);
    seg(-w / 2, -h / 2, w / 2, -h / 2); seg(w / 2, -h / 2, w / 2, h / 2); seg(w / 2, h / 2, -w / 2, h / 2); seg(-w / 2, h / 2, -w / 2, -h / 2);
    for (let i = 1; i < cols; i++) { const x = -w / 2 + (w * i) / cols; seg(x, -h / 2, x, h / 2); }
    for (let j = 1; j < rows; j++) { const y = -h / 2 + (h * j) / rows; seg(-w / 2, y, w / 2, y); }
    return lineGeometry(p);
}

type Mats = { face: THREE.ShaderMaterial; glass: THREE.ShaderMaterial; line: THREE.ShaderMaterial; fine: THREE.ShaderMaterial };

function Solid({ geometry, mats, position, rotation }: {
    geometry: THREE.BufferGeometry; mats: Mats; position: [number, number, number]; rotation?: [number, number, number];
}) {
    const edges = useMemo(() => new THREE.EdgesGeometry(geometry, 15), [geometry]);
    return (
        <group position={position} rotation={rotation}>
            <mesh geometry={geometry} material={mats.face} />
            <lineSegments geometry={edges} material={mats.line} />
        </group>
    );
}

function Window({ mats, position, rotationY = 0, w, h, cols = 2, rows = 2 }: {
    mats: Mats; position: [number, number, number]; rotationY?: number; w: number; h: number; cols?: number; rows?: number;
}) {
    const lines = useMemo(() => windowLines(w, h, cols, rows), [w, h, cols, rows]);
    return (
        <group position={position} rotation={[0, rotationY, 0]}>
            <mesh material={mats.glass}><planeGeometry args={[w, h]} /></mesh>
            <lineSegments geometry={lines} material={mats.line} />
        </group>
    );
}

const GROUND = -1.05;

function Scene({ lite }: { lite: boolean }) {
    const group = useRef<THREE.Group>(null);
    const uniforms = useMemo(() => ({
        uBuild: { value: START }, uSweep: { value: -1 }, uTime: { value: 0 }, uGround: { value: GROUND },
    }), []);
    const mats = useMemo<Mats>(() => {
        const make = (fragmentShader: string, color: string, opacity: number) => new THREE.ShaderMaterial({
            uniforms: { ...uniforms, uColor: { value: new THREE.Color(color) }, uOpacity: { value: opacity } },
            vertexShader: VERTEX, fragmentShader, transparent: true, depthWrite: false,
            side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
        });
        return {
            face: make(FACE_FRAGMENT, '#1E6BFF', 0.07),
            glass: make(FACE_FRAGMENT, '#5FC8FF', 0.16),
            line: make(LINE_FRAGMENT, '#7CCBFF', 1),
            fine: make(LINE_FRAGMENT, '#4C9DFF', 0.55),
        };
    }, [uniforms]);
    const floor = useMemo(() => new THREE.ShaderMaterial({
        uniforms,
        vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }',
        fragmentShader: FLOOR_FRAGMENT, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    }), [uniforms]);
    const geo = useMemo(() => ({
        body: new THREE.BoxGeometry(2.6, 1.1, 1.6),
        roof: gable(1.95, 0.85, 2.9),
        roofTiles: tiles(1.95, 0.85, 2.9, lite ? 5 : 7, lite ? 10 : 16),
        wing: new THREE.BoxGeometry(1.2, 1.1, 1.0),
        wingRoof: gable(1.45, 0.8, 1.2),
        wingTiles: tiles(1.45, 0.8, 1.2, lite ? 4 : 6, lite ? 5 : 7),
        porchFloor: new THREE.BoxGeometry(1.3, 0.08, 0.75),
        porchRoof: new THREE.BoxGeometry(1.4, 0.05, 0.85),
        column: new THREE.BoxGeometry(0.07, 0.86, 0.07),
        chimney: new THREE.BoxGeometry(0.22, 0.55, 0.22),
        floor: new THREE.PlaneGeometry(7, 7),
    }), [lite]);
    const t0 = useRef<number | null>(null);
    useFrame((state, dt) => {
        uniforms.uTime.value += dt;
        const now = state.clock.elapsedTime;
        if (t0.current === null) t0.current = now;
        const e = Math.min((now - t0.current) / BUILD, 1);
        uniforms.uBuild.value = START + (1 - Math.pow(1 - e, 3)) * (END - START + 0.1);
        // After the build, a sweep rises every SWEEP seconds (and pauses above the roof)
        const s = ((now - t0.current - BUILD) % SWEEP) / SWEEP;
        uniforms.uSweep.value = e < 1 ? -1 : START + s * 1.6 * (END - START);
        const g = group.current;
        if (!g) return;
        g.rotation.y = THREE.MathUtils.lerp(g.rotation.y, -0.6 + pointer.x * 0.6 + Math.sin(now * 0.2) * 0.1, 0.05);
        g.rotation.x = THREE.MathUtils.lerp(g.rotation.x, -pointer.y * 0.08, 0.05);
    });
    return (
        <group ref={group} position={[0, GROUND, 0]}>
            <mesh geometry={geo.floor} material={floor} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.001, 0]} />
            {/* Main block, gable roof along X */}
            <Solid geometry={geo.body} mats={mats} position={[0, 0.55, 0]} />
            <group position={[0, 1.1, 0]} rotation={[0, Math.PI / 2, 0]}>
                <Solid geometry={geo.roof} mats={mats} position={[0, 0, 0]} />
                <lineSegments geometry={geo.roofTiles} material={mats.fine} />
            </group>
            {/* Front wing with its own gable */}
            <Solid geometry={geo.wing} mats={mats} position={[0.6, 0.55, 1.3]} />
            <group position={[0.6, 1.1, 1.35]}>
                <Solid geometry={geo.wingRoof} mats={mats} position={[0, 0, 0]} />
                <lineSegments geometry={geo.wingTiles} material={mats.fine} />
            </group>
            {/* Porch */}
            <Solid geometry={geo.porchFloor} mats={mats} position={[-0.62, 0.04, 1.18]} />
            <Solid geometry={geo.porchRoof} mats={mats} position={[-0.62, 0.95, 1.2]} rotation={[0.12, 0, 0]} />
            {[[-1.2, 1.48], [-0.08, 1.48], [-1.2, 0.88]].map(([x, z]) => (
                <Solid key={`${x}${z}`} geometry={geo.column} mats={mats} position={[x, 0.5, z]} />
            ))}
            <Solid geometry={geo.chimney} mats={mats} position={[-0.8, 1.75, -0.3]} />
            {/* Windows and door */}
            <Window mats={mats} position={[0.6, 0.6, 1.805]} w={0.6} h={0.55} cols={3} rows={2} />
            <Window mats={mats} position={[0.6, 1.42, 1.96]} w={0.3} h={0.26} cols={2} rows={1} />
            <Window mats={mats} position={[-0.95, 0.55, 0.805]} w={0.42} h={0.5} />
            <Window mats={mats} position={[-0.35, 0.45, 0.805]} w={0.32} h={0.78} cols={1} rows={3} />
            <Window mats={mats} position={[1.305, 0.6, -0.35]} rotationY={Math.PI / 2} w={0.5} h={0.5} />
            <Window mats={mats} position={[1.205, 0.6, 1.3]} rotationY={Math.PI / 2} w={0.45} h={0.5} />
            <Window mats={mats} position={[-1.305, 0.6, -0.2]} rotationY={Math.PI / 2} w={0.55} h={0.5} cols={3} />
            <Window mats={mats} position={[0.3, 0.6, -0.805]} w={0.7} h={0.5} cols={3} />
        </group>
    );
}

export default function House({ active, lite }: { active: boolean; lite: boolean }) {
    useEffect(() => {
        const move = (e: PointerEvent) => {
            pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
            pointer.y = -((e.clientY / window.innerHeight) * 2 - 1);
        };
        window.addEventListener('pointermove', move, { passive: true });
        return () => window.removeEventListener('pointermove', move);
    }, []);
    return (
        <Canvas
            frameloop={active ? 'always' : 'never'}
            dpr={lite ? [1, 1.25] : [1, 1.75]}
            camera={{ position: lite ? [5.4, 3.7, 7.9] : [4.4, 3.0, 6.4], fov: 38 }}
            onCreated={({ camera }) => camera.lookAt(0.15, 0, 0.3)}
            gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
            style={{ pointerEvents: 'none' }}
        >
            <Scene lite={lite} />
        </Canvas>
    );
}
