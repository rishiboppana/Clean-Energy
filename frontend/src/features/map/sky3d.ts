// Realistic Earth, sun, moon and stars for the globe's three.js scene (globe radius is 100 units).
// Sun and Moon directions are exact (sky.ts); distances and sizes are compressed so everything fits on screen.
// Imagery: NASA Blue Marble day map and city-lights night map (via three-globe's examples), static clouds, Moon texture (three.js examples).
import * as THREE from 'three'
import type { GlobeMethods } from 'react-globe.gl'
import { subpoint } from './sky'

const R = 100
const SUN_DIST = 1500
const MOON_DIST = 330
const MOON_R = 0.273 * R // real Moon/Earth radius ratio

const loader = new THREE.TextureLoader()
const tex = (name: string, srgb = true) => {
  const t = loader.load(`/textures/${name}`)
  if (srgb) t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 8
  return t
}

// Day map on the lit side, city lights on the dark side, a warm twilight band on the terminator, and a sun glint on the ocean.
const VERT = `
varying vec3 vNormalW; varying vec3 vPosW; varying vec2 vUv;
void main() {
  vUv = uv;
  vNormalW = normalize(mat3(modelMatrix) * normal);
  vPosW = (modelMatrix * vec4(position, 1.0)).xyz;
  gl_Position = projectionMatrix * viewMatrix * vec4(vPosW, 1.0);
}`
const FRAG = `
uniform sampler2D dayMap; uniform sampler2D nightMap; uniform sampler2D waterMask; uniform vec3 sunDir;
varying vec3 vNormalW; varying vec3 vPosW; varying vec2 vUv;
void main() {
  vec3 n = normalize(vNormalW);
  float d = dot(n, sunDir);
  float day = smoothstep(-0.18, 0.4, d);
  vec3 dayCol = texture2D(dayMap, vUv).rgb * (0.55 + 0.6 * clamp(d, 0.0, 1.0));
  vec3 nightCol = texture2D(nightMap, vUv).rgb * 1.25 + vec3(0.004, 0.008, 0.02);
  vec3 col = mix(nightCol, dayCol, day);
  col += vec3(1.0, 0.45, 0.15) * 0.1 * smoothstep(0.3, 0.0, abs(d - 0.05)) * (0.4 + 0.6 * day); // twilight glow
  vec3 v = normalize(cameraPosition - vPosW);
  float glint = pow(max(dot(reflect(-sunDir, n), v), 0.0), 60.0) * texture2D(waterMask, vUv).r * smoothstep(0.0, 0.2, d);
  col += vec3(1.0, 0.95, 0.8) * glint * 0.9;
  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}`

export function createEarthMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      dayMap: { value: tex('earth-day.jpg') }, nightMap: { value: tex('earth-night.jpg') },
      waterMask: { value: tex('earth-water.png', false) }, sunDir: { value: new THREE.Vector3(1, 0, 0) },
    },
    vertexShader: VERT, fragmentShader: FRAG,
  })
}

function glowTexture() {
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const g = c.getContext('2d')!
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  grad.addColorStop(0, 'rgba(255,244,200,1)')
  grad.addColorStop(0.25, 'rgba(255,220,140,0.6)')
  grad.addColorStop(1, 'rgba(255,200,100,0)')
  g.fillStyle = grad
  g.fillRect(0, 0, 128, 128)
  return new THREE.CanvasTexture(c)
}

export function addSky(globe: GlobeMethods, earth: THREE.ShaderMaterial) {
  const scene = globe.scene()
  const cam = globe.camera() as THREE.PerspectiveCamera
  cam.far = 6000
  cam.updateProjectionMatrix()

  const sunLight = new THREE.DirectionalLight(0xfff2dd, 2.6) // lights the clouds and the Moon; the Earth surface has its own shader
  const ambient = new THREE.AmbientLight(0x6f84b0, 0.35)
  globe.lights([ambient, sunLight])

  const sun = new THREE.Mesh(new THREE.SphereGeometry(22, 32, 32), new THREE.MeshBasicMaterial({ color: 0xfff1b0 }))
  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), blending: THREE.AdditiveBlending, depthWrite: false }))
  glow.scale.setScalar(130)
  const moon = new THREE.Mesh(new THREE.SphereGeometry(MOON_R, 64, 64), new THREE.MeshLambertMaterial({ map: tex('moon_1024.jpg') }))
  const clouds = new THREE.Mesh(
    new THREE.SphereGeometry(R * 1.008, 64, 64),
    new THREE.MeshLambertMaterial({ map: tex('earth_clouds_1024.png'), transparent: true, opacity: 0.8, depthWrite: false }),
  )
  scene.add(sun, glow, moon, clouds)

  const dir = (body: 'Sun' | 'Moon', date: Date) => {
    const { lat, lng } = subpoint(body, date)
    const c = globe.getCoords(lat, lng, 0) // surface point under the body, in scene coordinates
    return new THREE.Vector3(c.x, c.y, c.z).normalize()
  }

  return {
    update(date: Date) {
      const s = dir('Sun', date)
      earth.uniforms.sunDir.value.copy(s)
      sunLight.position.copy(s).multiplyScalar(SUN_DIST)
      sun.position.copy(s).multiplyScalar(SUN_DIST)
      glow.position.copy(sun.position)
      moon.position.copy(dir('Moon', date)).multiplyScalar(MOON_DIST)
    },
    dispose() {
      scene.remove(sun, glow, moon, clouds)
    },
  }
}
