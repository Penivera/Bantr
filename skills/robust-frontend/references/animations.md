# Animation Patterns Reference

## Framer Motion

### Page Transitions (with TanStack Router)
```tsx
import { motion, AnimatePresence } from 'framer-motion'

const pageVariants = {
  initial: { opacity: 0, x: -20 },
  enter: { opacity: 1, x: 0, transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] } },
  exit: { opacity: 0, x: 20, transition: { duration: 0.2 } },
}

export function PageTransition({ children }: { children: React.ReactNode }) {
  return (
    <AnimatePresence mode="wait">
      <motion.div key={location.pathname} variants={pageVariants} initial="initial" animate="enter" exit="exit">
        {children}
      </motion.div>
    </AnimatePresence>
  )
}
```

### Staggered List Animation
```tsx
const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.1 },
  },
}
const item = {
  hidden: { opacity: 0, y: 24, scale: 0.96 },
  show: { opacity: 1, y: 0, scale: 1, transition: { type: 'spring', damping: 20, stiffness: 200 } },
}

<motion.ul variants={container} initial="hidden" animate="show">
  {items.map(item => (
    <motion.li key={item.id} variants={item}>{item.name}</motion.li>
  ))}
</motion.ul>
```

### Gesture / Drag
```tsx
<motion.div
  drag="x"
  dragConstraints={{ left: -100, right: 100 }}
  whileDrag={{ scale: 1.05, cursor: 'grabbing' }}
  whileHover={{ scale: 1.02 }}
  whileTap={{ scale: 0.98 }}
/>
```

### Layout Animations (auto-animate between states)
```tsx
<motion.div layout layoutId="card-1">
  {/* Framer Motion handles FLIP automatically */}
</motion.div>
```

### useMotionValue + useTransform (scroll-linked)
```tsx
import { useScroll, useTransform, motion } from 'framer-motion'
const { scrollYProgress } = useScroll()
const scale = useTransform(scrollYProgress, [0, 1], [1, 1.5])
const opacity = useTransform(scrollYProgress, [0, 0.5], [1, 0])

<motion.div style={{ scale, opacity }} />
```

---

## GSAP

### Setup (always register plugins)
```ts
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { TextPlugin } from 'gsap/TextPlugin'
import { useGSAP } from '@gsap/react'
gsap.registerPlugin(ScrollTrigger, TextPlugin, useGSAP)
```

### Hero Intro Timeline
```tsx
const containerRef = useRef<HTMLDivElement>(null)

useGSAP(() => {
  const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
  tl.from('.hero-eyebrow', { y: 30, opacity: 0, duration: 0.6 })
    .from('.hero-title', { y: 50, opacity: 0, duration: 0.8 }, '-=0.3')
    .from('.hero-subtitle', { y: 30, opacity: 0, duration: 0.6 }, '-=0.4')
    .from('.hero-cta', { y: 20, opacity: 0, duration: 0.5, stagger: 0.1 }, '-=0.3')
}, { scope: containerRef })
```

### ScrollTrigger — pin + scrub
```tsx
useGSAP(() => {
  gsap.to('.parallax-bg', {
    yPercent: -30,
    ease: 'none',
    scrollTrigger: {
      trigger: '.section',
      start: 'top bottom',
      end: 'bottom top',
      scrub: true,
    },
  })

  // Pin a section while scrolling through it
  ScrollTrigger.create({
    trigger: '.sticky-section',
    pin: true,
    start: 'top top',
    end: '+=500',
    scrub: 1,
  })
}, { scope: containerRef })
```

### Text Reveal (character by character)
```tsx
import { SplitText } from 'gsap/SplitText' // Club GSAP plugin
gsap.registerPlugin(SplitText)

useGSAP(() => {
  const split = new SplitText('.title', { type: 'chars,words' })
  gsap.from(split.chars, {
    opacity: 0, y: 40, rotateX: -90,
    stagger: 0.02, duration: 0.6, ease: 'back.out(1.7)',
  })
  return () => split.revert()
}, { scope: containerRef })
```

### Cleanup — always use useGSAP scope
```tsx
// useGSAP automatically creates a context and reverts all tweens/triggers on unmount
useGSAP(() => { /* safe — auto cleanup */ }, { scope: ref })
// NEVER do this — no cleanup:
// useEffect(() => { gsap.to(...) }, [])
```

---

## AOS (Animate on Scroll)

### Initialization (once, in root component or layout)
```tsx
import AOS from 'aos'
import 'aos/dist/aos.css'

useEffect(() => {
  AOS.init({
    duration: 700,
    easing: 'ease-out-cubic',
    once: true,         // animate only once per element
    offset: 80,         // trigger 80px before element enters view
    delay: 0,
  })
  return () => AOS.refresh()
}, [])
```

### Usage (declarative HTML attributes)
```tsx
// Available animations: fade, fade-up, fade-down, fade-left, fade-right,
// flip-left, flip-right, zoom-in, zoom-out, slide-up
<div data-aos="fade-up">Element 1</div>
<div data-aos="fade-up" data-aos-delay="100">Element 2</div>
<div data-aos="zoom-in" data-aos-duration="1000" data-aos-easing="ease-in-sine">Element 3</div>
<div data-aos="flip-left" data-aos-anchor=".trigger-element">Anchored</div>
```

### Refresh after dynamic content
```tsx
useEffect(() => { AOS.refresh() }, [dynamicContent])
```

---

## Three.js + React Three Fiber

### Basic 3D Scene
```tsx
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Environment, Float, Text3D } from '@react-three/drei'
import { useRef } from 'react'
import * as THREE from 'three'

function RotatingBox() {
  const meshRef = useRef<THREE.Mesh>(null)
  useFrame((_, delta) => {
    if (meshRef.current) meshRef.current.rotation.y += delta * 0.5
  })
  return (
    <mesh ref={meshRef}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="#4f46e5" roughness={0.3} metalness={0.8} />
    </mesh>
  )
}

export function Scene() {
  return (
    <Canvas
      camera={{ position: [0, 0, 5], fov: 60 }}
      gl={{ antialias: true, alpha: true }}
      style={{ background: 'transparent' }}
    >
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1} castShadow />
      <Float speed={2} rotationIntensity={0.5} floatIntensity={1}>
        <RotatingBox />
      </Float>
      <OrbitControls enableZoom={false} />
      <Environment preset="city" />
    </Canvas>
  )
}
```

### Particle System
```tsx
import { Points, PointMaterial } from '@react-three/drei'
import { useMemo } from 'react'

function Particles({ count = 3000 }) {
  const positions = useMemo(() => {
    const arr = new Float32Array(count * 3)
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 10
      arr[i * 3 + 1] = (Math.random() - 0.5) * 10
      arr[i * 3 + 2] = (Math.random() - 0.5) * 10
    }
    return arr
  }, [count])

  return (
    <Points positions={positions} frustumCulled={false}>
      <PointMaterial size={0.02} color="#818cf8" sizeAttenuation transparent opacity={0.8} />
    </Points>
  )
}
```

### Disposal (memory management)
```tsx
import { useEffect } from 'react'
function Model({ geometry }: { geometry: THREE.BufferGeometry }) {
  useEffect(() => {
    return () => { geometry.dispose() }  // cleanup on unmount
  }, [geometry])
  return <mesh geometry={geometry} />
}
```

### GSAP + Three.js (animate 3D objects with GSAP timelines)
```tsx
useGSAP(() => {
  if (!meshRef.current) return
  gsap.to(meshRef.current.rotation, { y: Math.PI * 2, duration: 4, repeat: -1, ease: 'none' })
  gsap.to(meshRef.current.position, { y: 0.5, duration: 2, yoyo: true, repeat: -1, ease: 'power1.inOut' })
})
```

---

## Combining Libraries — Common Patterns

### Marketing Landing Page
```
Hero: GSAP timeline (cinematic intro) + Three.js background
Features: AOS scroll reveal (fade-up cards)
Interactive: Framer Motion (hover states, modal transitions)
```

### Dashboard / App
```
Route transitions: Framer Motion AnimatePresence
List updates: Framer Motion layout animations
Charts: CSS transitions or Recharts built-in animations
Notifications: Framer Motion (slide-in toast)
```

### Product / E-commerce
```
3D product viewer: Three.js + OrbitControls
Page transitions: Framer Motion
Cart animations: Framer Motion layout
Scroll sections: GSAP ScrollTrigger
```
