/* Schedule clicks before their deadlines. The media and clicks share an output graph.
 * Media currentTime remains the song clock; no change to model timestamps.
 * This is a look-ahead media scheduler, not sample-accurate transport.
 */
(() => {
 'use strict';
 class PlaybackSync {
  constructor(media, getGrid) {
   this.media=media;this.getGrid=getGrid;this.context=null;this.enabled=false;
   this.nodes=new Set();this.scheduled=new Set();this.timer=null;this.ready=false;
   media.addEventListener('playing',()=>{this.ready=true;this.restart();});
   for(const event of ['pause','waiting','seeking','ended','emptied'])media.addEventListener(event,()=>{this.ready=false;this.clear();});
   media.addEventListener('seeked',()=>{this.ready=!media.paused&&media.readyState>=3;this.restart();});
   media.addEventListener('ratechange',()=>this.restart());
  }
  async prepare() {
   if(!this.context){
    this.context=new AudioContext({latencyHint:'interactive'});
    this.source=this.context.createMediaElementSource(this.media);
    this.source.connect(this.context.destination);
   }
   await this.context.resume();
  }
  async enable(value) {
   this.enabled=value;this.clear();
   if(value){await this.prepare();this.ready=!this.media.paused&&this.media.readyState>=3;this.restart();}
  }
  clear() {
   clearInterval(this.timer);this.timer=null;
   for(const node of this.nodes){try{node.stop();}catch{ /* already ended */ }}
   this.nodes.clear();this.scheduled.clear();
  }
  restart() {
   this.clear();
   if(!this.enabled||!this.ready||this.media.paused||!this.context)return;
   this.tick();this.timer=setInterval(()=>this.tick(),25);
  }
  tick() {
   const a=this.media,c=this.context;
   if(!this.enabled||!this.ready||a.paused||a.seeking||c.state!=='running')return;
   const {beats,downbeats,endSec}=this.getGrid(),now=a.currentTime,rate=a.playbackRate;
   const ctxNow=c.currentTime;
   for(let i=0;i<beats.length;i++) {
    const t=beats[i],delay=(t-now)/rate;
    if(t>=endSec||delay>.15)break;
    // Skip missed deadlines rather than playing a late burst after a stall.
    if(delay<-.025||this.scheduled.has(i))continue;
    this.scheduled.add(i);
    this.click(ctxNow+Math.max(.003,delay),downbeats.some(d=>Math.abs(d-t)<.025));
   }
  }
  click(when,strong) {
   const c=this.context,o=c.createOscillator(),g=c.createGain();
   o.frequency.value=strong?1250:850;
   g.gain.setValueAtTime(.045,when);g.gain.exponentialRampToValueAtTime(.001,when+.035);
   o.connect(g);g.connect(c.destination);this.nodes.add(o);
   o.onended=()=>{this.nodes.delete(o);o.disconnect();g.disconnect();};
   o.start(when);o.stop(when+.04);
  }
 }
 window.LowEndPlaybackSync=PlaybackSync;
})();
