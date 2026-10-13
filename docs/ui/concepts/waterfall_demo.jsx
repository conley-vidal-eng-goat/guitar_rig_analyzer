import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";

const W = 720;
const H = 900;
const FREQ_BINS = 96;
const TIME_SLICES = 80;
const PW = 8;
const PD = 10;
const MH = 3.0;
const CD = 12;
const DHZ = 10.8;

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function lerp(a, b, t) { return a + (b - a) * t; }
function logFreq(i, n) { return 20 * Math.pow(1000, n <= 1 ? 0 : i/(n-1)); }
function fmtFreq(f) {
  if (f >= 10000) return (f/1000).toFixed(1)+" kHz";
  if (f >= 1000) return (f/1000).toFixed(2)+" kHz";
  return Math.round(f)+" Hz";
}

function ampColor(a, c) {
  const t = clamp(a, 0, 1);
  if (t < 0.15) { const s=t/0.15; c.setRGB(0.02+s*0.05,0.02+s*0.08,0.08+s*0.35); }
  else if (t < 0.35) { const s=(t-0.15)/0.2; c.setRGB(0.07,0.1+s*0.55,0.43+s*0.45); }
  else if (t < 0.55) { const s=(t-0.35)/0.2; c.setRGB(0.07+s*0.15,0.65+s*0.2,0.88-s*0.55); }
  else if (t < 0.72) { const s=(t-0.55)/0.17; c.setRGB(0.22+s*0.68,0.85+s*0.1,0.33-s*0.25); }
  else if (t < 0.88) { const s=(t-0.72)/0.16; c.setRGB(0.9+s*0.1,0.95-s*0.6,0.08-s*0.04); }
  else { const s=(t-0.88)/0.12; c.setRGB(1.0,0.35+s*0.6,0.04+s*0.7); }
  return c;
}

function demoSpec(t) {
  const o = new Float32Array(FREQ_BINS);
  for (let i = 0; i < FREQ_BINS; i++) {
    const f = logFreq(i, FREQ_BINS);
    let a = 0;
    const fund = 110 + Math.sin(t*0.3)*28;
    for (let h = 1; h <= 8; h++) {
      const d = Math.abs(Math.log2(f/(fund*h)));
      if (d < 0.15) a += (1/h)*(0.7+0.3*Math.sin(t*1.2+h))*(1-d/0.15);
    }
    a += 0.03 + Math.sin(i*7.3+t*2.1)*0.015;
    const sw = 800+Math.sin(t*0.18)*600;
    const sd = Math.abs(Math.log2(f/sw));
    if (sd < 0.3) a += 0.35*(1-sd/0.3)*(0.5+0.5*Math.sin(t*0.7));
    o[i] = clamp(a, 0, 1);
  }
  return o;
}

export default function App() {
  const mRef = useRef(null);
  const oRef = useRef(null);
  const rRef = useRef(null);
  const aRef = useRef(null);
  const tRef = useRef(null);
  const hist = useRef(new Float32Array(FREQ_BINS*TIME_SLICES));
  const latest = useRef(new Float32Array(FREQ_BINS));
  const disp = useRef(new Float32Array(FREQ_BINS));
  const rot = useRef({ x:-0.45, y:-0.3, tx:-0.45, ty:-0.3 });
  const ptr = useRef({ dn:false, x:0, y:0 });
  const info = useRef({ f:"440 Hz", a:"0%", n:0 });
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const el = mRef.current, ov = oRef.current;
    if (!el || !ov) return;
    const ctx = ov.getContext("2d");
    const sc = new THREE.Scene();
    sc.background = new THREE.Color(0x04070b);
    const cam = new THREE.PerspectiveCamera(40, W/H, 0.1, 100);
    const ren = new THREE.WebGLRenderer({ antialias:true, powerPreference:"high-performance" });
    ren.setPixelRatio(1); ren.setSize(W, H);
    el.appendChild(ren.domElement);
    rRef.current = ren;

    sc.add(new THREE.AmbientLight(0xffffff, 0.5));
    const kl = new THREE.DirectionalLight(0xffffff, 0.8);
    kl.position.set(2, 8, 4); sc.add(kl);
    const sl = new THREE.DirectionalLight(0x6688aa, 0.3);
    sl.position.set(-5, 3, -2); sc.add(sl);

    const geo = new THREE.PlaneGeometry(PW, PD, FREQ_BINS-1, TIME_SLICES-1);
    geo.rotateX(-Math.PI/2);
    const vn = geo.attributes.position.count;
    const cs = new Float32Array(vn*3);
    for (let i=0;i<vn;i++){cs[i*3]=0.02;cs[i*3+1]=0.02;cs[i*3+2]=0.08;}
    geo.setAttribute("color", new THREE.BufferAttribute(cs, 3));
    const mt = new THREE.MeshStandardMaterial({ vertexColors:true, side:THREE.DoubleSide, roughness:0.5, metalness:0.1 });
    const mesh = new THREE.Mesh(geo, mt); sc.add(mesh);

    const gg = new THREE.PlaneGeometry(PW+1, PD+1, 12, 10);
    gg.rotateX(-Math.PI/2);
    const gm = new THREE.MeshBasicMaterial({ color:0x1a2535, wireframe:true, transparent:true, opacity:0.12 });
    const grid = new THREE.Mesh(gg, gm); grid.position.y=-0.02; sc.add(grid);

    const rlg = new THREE.CylinderGeometry(0.025, 0.025, MH*0.8, 6);
    const rlm = new THREE.MeshBasicMaterial({ color:0x00ddff, transparent:true, opacity:0.7 });
    const refL = new THREE.Mesh(rlg, rlm); sc.add(refL);
    const rdg = new THREE.SphereGeometry(0.055, 10, 10);
    const rdm = new THREE.MeshBasicMaterial({ color:0x00ffee });
    const refD = new THREE.Mesh(rdg, rdm); sc.add(refD);

    const pos = geo.attributes.position;
    const col = geo.attributes.color;
    const tc = new THREE.Color();
    const h = hist.current;

    function push() {
      h.copyWithin(FREQ_BINS, 0, FREQ_BINS*(TIME_SLICES-1));
      h.set(disp.current, 0);
    }
    function updMesh() {
      for (let t=0; t<TIME_SLICES; t++) {
        for (let f=0; f<FREQ_BINS; f++) {
          const vi=t*FREQ_BINS+f;
          const a=h[t*FREQ_BINS+f];
          pos.setY(vi, a*MH);
          ampColor(a, tc);
          col.setXYZ(vi, tc.r, tc.g, tc.b);
        }
      }
      pos.needsUpdate=true; col.needsUpdate=true;
      geo.computeVertexNormals();
    }
    function updRef() {
      const cx=cam.position.x, cz=cam.position.z;
      const ln=Math.sqrt(cx*cx+cz*cz);
      if (ln<0.01) return;
      const ang=Math.atan2(cx,cz);
      const hw=PW/2;
      const px=clamp(Math.sin(ang)*hw*1.5, -hw, hw);
      const bt=(px+hw)/PW;
      const bi=clamp(Math.round(bt*(FREQ_BINS-1)), 0, FREQ_BINS-1);
      const fr=logFreq(bi, FREQ_BINS);
      const xp=-hw+(bi/(FREQ_BINS-1))*PW;
      const fz=PD/2;
      refL.position.set(xp, MH*0.4, fz);
      refD.position.set(xp, 0.01, fz);
      const a=disp.current[bi];
      info.current = { f:fmtFreq(fr), a:(a*100).toFixed(0)+"%", n:a };
    }
    function drawOv() {
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle="rgba(255,255,255,0.92)";
      ctx.font="600 30px system-ui, sans-serif";
      ctx.fillText("Waterfall Spectrum", 18, 38);
      ctx.fillStyle="rgba(180,195,210,0.65)";
      ctx.font="500 15px system-ui, sans-serif";
      ctx.fillText("Frequency × Time × Amplitude  ·  newest at front", 18, 60);
      const lx=18,ly=76,lw=180,lh=12;
      const gr=ctx.createLinearGradient(lx,0,lx+lw,0);
      gr.addColorStop(0,"#060818"); gr.addColorStop(0.2,"#1466aa");
      gr.addColorStop(0.4,"#14aacc"); gr.addColorStop(0.55,"#40cc50");
      gr.addColorStop(0.7,"#ddcc22"); gr.addColorStop(0.85,"#ee5500");
      gr.addColorStop(1.0,"#ffccaa");
      ctx.fillStyle=gr; ctx.fillRect(lx,ly,lw,lh);
      ctx.fillStyle="rgba(160,175,190,0.5)";
      ctx.font="500 11px system-ui"; ctx.fillText("quiet",lx,ly+22);
      ctx.textAlign="right"; ctx.fillText("loud",lx+lw,ly+22); ctx.textAlign="left";

      const nfo=info.current;
      ctx.shadowColor="rgba(0,221,255,0.5)"; ctx.shadowBlur=12;
      ctx.fillStyle="rgba(0,221,255,0.95)";
      ctx.font="700 26px 'JetBrains Mono', monospace";
      ctx.fillText(nfo.f, 18, H-44);
      ctx.shadowBlur=0;
      ampColor(nfo.n, tc);
      ctx.fillStyle=`rgb(${(tc.r*255)|0},${(tc.g*255)|0},${(tc.b*255)|0})`;
      ctx.font="600 20px 'JetBrains Mono', monospace";
      ctx.fillText("amplitude: "+nfo.a, 18, H-20);
    }
    function sync() {
      const d=disp.current, l=latest.current;
      for (let i=0;i<FREQ_BINS;i++) d[i]=lerp(d[i],l[i],0.22);
    }

    let acc=0;
    function loop() {
      aRef.current=requestAnimationFrame(loop);
      if (!rRef.current) return;
      sync();
      acc+=1/60;
      if (acc>=1/DHZ) { acc-=1/DHZ; push(); }
      updMesh();
      const r=rot.current;
      r.x=lerp(r.x,r.tx,0.07); r.y=lerp(r.y,r.ty,0.07);
      if (!ptr.current.dn && !paused) r.ty-=0.0008;
      cam.position.set(
        Math.sin(r.y)*Math.cos(r.x)*CD,
        -Math.sin(r.x)*CD,
        Math.cos(r.y)*Math.cos(r.x)*CD
      );
      cam.lookAt(0, 0.5, 0);
      updRef(); ren.render(sc, cam); drawOv();
    }

    const cv=ren.domElement;
    const pd=(x,y)=>{ptr.current={dn:true,x,y};};
    const pu=()=>{ptr.current.dn=false;};
    const pm=(x,y)=>{
      if (!ptr.current.dn) return;
      rot.current.ty-=(x-ptr.current.x)*0.006;
      rot.current.tx+=(y-ptr.current.y)*0.004;
      ptr.current.x=x; ptr.current.y=y;
    };
    cv.addEventListener("mousedown",e=>pd(e.clientX,e.clientY));
    cv.addEventListener("mousemove",e=>pm(e.clientX,e.clientY));
    cv.addEventListener("mouseup",pu); cv.addEventListener("mouseleave",pu);
    cv.addEventListener("touchstart",e=>{const t2=e.touches[0];pd(t2.clientX,t2.clientY);},{passive:true});
    cv.addEventListener("touchmove",e=>{e.preventDefault();const t2=e.touches[0];pm(t2.clientX,t2.clientY);},{passive:false});
    cv.addEventListener("touchend",pu);

    let dt=0;
    tRef.current=setInterval(()=>{
      dt+=1/DHZ; latest.current=demoSpec(dt);
    }, 1000/DHZ);

    loop();

    return ()=>{
      if (tRef.current) clearInterval(tRef.current);
      if (aRef.current) cancelAnimationFrame(aRef.current);
      ren.dispose(); geo.dispose(); mt.dispose(); gg.dispose(); gm.dispose();
      rlg.dispose(); rlm.dispose(); rdg.dispose(); rdm.dispose();
      if (el.contains(ren.domElement)) el.removeChild(ren.domElement);
    };
  }, [paused]);

  return (
    <div className="flex flex-col items-center bg-black min-h-screen p-3">
      <div style={{position:"relative",width:W,height:H,borderRadius:18,overflow:"hidden",
        boxShadow:"0 16px 48px rgba(0,0,0,0.5)",border:"1px solid rgba(255,255,255,0.06)"}}>
        <div ref={mRef} style={{position:"absolute",inset:0,cursor:"grab"}} />
        <canvas ref={oRef} width={W} height={H} style={{position:"absolute",inset:0,pointerEvents:"none"}} />
        <button onClick={()=>setPaused(v=>!v)}
          style={{position:"absolute",right:16,top:16,zIndex:5,
            border:"1px solid rgba(255,255,255,0.15)",background:"rgba(17,24,39,0.7)",
            color:"#fff",borderRadius:999,padding:"8px 14px",fontSize:14,
            backdropFilter:"blur(8px)"}}>
          {paused?"Resume":"Pause"}
        </button>
      </div>
      <p className="text-xs text-gray-600 mt-3">Drag to orbit · Cyan marker tracks frequency · Color = amplitude</p>
    </div>
  );
}
