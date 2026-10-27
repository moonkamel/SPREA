import { useMemo, useRef } from 'react';
import { Canvas, useFrame, type ThreeEvent } from '@react-three/fiber';
import * as THREE from 'three';

// "Your area" scene: a field of homes as points in the official DPE colours.
// The cursor (or finger) parts the field like a lens and lights up the F and G
// homes around it. Illustration: the points are not real addresses.

const COLORS = ['#009C6D', '#52B153', '#78BD76', '#F4E70F', '#F0B40F', '#EB8235', '#D7221F'];
// Rough share of each class in the housing stock, for the look of the field
const SHARE = [0.02, 0.04, 0.12, 0.31, 0.27, 0.15, 0.09];

const VERTEX = /* glsl */ `
uniform float uTime; uniform vec2 uMouse; uniform float uPower; uniform float uPixel;
attribute vec3 aColor; attribute float aPassoire; attribute float aSeed;
varying vec3 vColor; varying float vGlow; varying float vDim;
void main(){
  vec3 p=position;
  vec2 d=p.xy-uMouse; float dist=length(d);
  float lens=(1.-smoothstep(0.,1.6,dist))*uPower;
  p.xy+=normalize(d+1e-4)*lens*0.55;                 // pushed aside
  p.z+=lens*(0.6+aPassoire*1.2)+sin(uTime*1.3+aSeed*6.28)*0.04; // lifted, F/G higher
  vGlow=aPassoire*(0.08+lens*1.8+0.12*sin(uTime*2.+aSeed*12.));
  vDim=0.5+lens*0.8;
  vColor=aColor;
  vec4 mv=modelViewMatrix*vec4(p,1.);
  gl_PointSize=uPixel*(1.0+aPassoire*0.5+lens*(0.8+aPassoire*1.6))*(6./-mv.z);
  gl_Position=projectionMatrix*mv;
}`;

const FRAGMENT = /* glsl */ `
varying vec3 vColor; varying float vGlow; varying float vDim;
void main(){
  float d=length(gl_PointCoord-.5);
  float core=(1.-smoothstep(.15,.5,d));
  float halo=(1.-smoothstep(0.,.5,d))*vGlow;
  vec3 col=vColor*(0.5+core*0.5)*vDim+vColor*halo*1.5;
  float a=core*min(vDim,1.)+halo*0.7;
  if(a<0.02) discard;
  gl_FragColor=vec4(col,a);
}`;

function Field({ cols, rows }: { cols: number; rows: number }) {
    const mat = useRef<THREE.ShaderMaterial>(null);
    const target = useRef(new THREE.Vector2(99, 99));
    const power = useRef(0);
    const { positions, colors, passoire, seeds } = useMemo(() => {
        const n = cols * rows;
        const positions = new Float32Array(n * 3), colors = new Float32Array(n * 3);
        const passoire = new Float32Array(n), seeds = new Float32Array(n);
        const c = new THREE.Color();
        const w = 11, h = w * (rows / cols);
        let k = 0;
        for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++, k++) {
            positions.set([(x / (cols - 1) - 0.5) * w + (Math.random() - 0.5) * 0.08, (y / (rows - 1) - 0.5) * h + (Math.random() - 0.5) * 0.08, 0], k * 3);
            let r = Math.random(), cls = 0;
            while (cls < 6 && r > SHARE[cls]) { r -= SHARE[cls]; cls++; }
            c.set(COLORS[cls]);
            colors.set([c.r, c.g, c.b], k * 3);
            passoire[k] = cls >= 5 ? 1 : 0;
            seeds[k] = Math.random();
        }
        return { positions, colors, passoire, seeds };
    }, [cols, rows]);
    const uniforms = useMemo(() => ({
        uTime: { value: 0 }, uMouse: { value: new THREE.Vector2(99, 99) }, uPower: { value: 0 },
        uPixel: { value: Math.max(Math.min(window.devicePixelRatio, 2), 1.5) * 2.6 },
    }), []);
    useFrame((state, dt) => {
        uniforms.uTime.value += dt;
        // Without a pointer, the lens wanders on its own
        const idle = power.current < 0.5;
        const t = state.clock.elapsedTime;
        const goal = idle ? new THREE.Vector2(Math.sin(t * 0.35) * 3.5, Math.cos(t * 0.27) * 1.6) : target.current;
        uniforms.uMouse.value.lerp(goal, idle ? 0.03 : 0.15);
        uniforms.uPower.value = THREE.MathUtils.lerp(uniforms.uPower.value, idle ? 0.7 : 1, 0.06);
        power.current = Math.max(0, power.current - dt * 0.5);
    });
    const onMove = (e: ThreeEvent<PointerEvent>) => {
        target.current.set(e.point.x, e.point.y);
        power.current = 2;
    };
    return (
        <group rotation={[-0.55, 0, 0]}>
            <points>
                <bufferGeometry>
                    <bufferAttribute attach="attributes-position" args={[positions, 3]} />
                    <bufferAttribute attach="attributes-aColor" args={[colors, 3]} />
                    <bufferAttribute attach="attributes-aPassoire" args={[passoire, 1]} />
                    <bufferAttribute attach="attributes-aSeed" args={[seeds, 1]} />
                </bufferGeometry>
                <shaderMaterial ref={mat} vertexShader={VERTEX} fragmentShader={FRAGMENT} uniforms={uniforms}
                    transparent depthWrite={false} blending={THREE.AdditiveBlending} />
            </points>
            {/* Invisible plane catching the pointer */}
            <mesh onPointerMove={onMove} visible={false}>
                <planeGeometry args={[14, 10]} />
                <meshBasicMaterial />
            </mesh>
        </group>
    );
}

export default function SectorField({ active, lite }: { active: boolean; lite: boolean }) {
    return (
        <Canvas
            frameloop={active ? 'always' : 'never'}
            dpr={lite ? [1, 1.25] : [1, 1.75]}
            camera={{ position: [0, 0, 7.5], fov: 45 }}
            gl={{ antialias: false, alpha: true, powerPreference: 'high-performance' }}
        >
            <Field cols={lite ? 54 : 96} rows={lite ? 30 : 50} />
        </Canvas>
    );
}
