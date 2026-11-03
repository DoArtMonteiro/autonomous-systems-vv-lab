// The shared time cursor of a run workspace. Every view (scene, charts, timeline, verification)
// subscribes to it; changes are coalesced and delivered once per animation frame, so scrubbing never
// does more work than one frame can show. Playback advances logical record time only: it is a
// viewing aid and never feeds anything back into a simulation.

import { lowerIndex } from './dom.js';

export class TimeCursor {
  constructor({ t0, t1, unit, samples, events }) {
    this.t0 = t0;
    this.t1 = t1;
    this.unit = unit;
    this.samples = samples && samples.length ? samples : [t0, t1];
    this.eventTimes = [...new Set((events || []).map((e) => e.t).filter(Number.isFinite))].sort((a, b) => a - b);
    this.t = t0;
    this.playing = false;
    this.speed = 1;
    this.subs = new Set();
    this.playSubs = new Set();
    this.dirty = false;
    this.frame = 0;
    this.last = 0;
    this.tick = this.tick.bind(this);
  }

  subscribe(fn) {
    this.subs.add(fn);
    return () => this.subs.delete(fn);
  }

  onPlayState(fn) {
    this.playSubs.add(fn);
    return () => this.playSubs.delete(fn);
  }

  set(t) {
    const c = Math.min(this.t1, Math.max(this.t0, t));
    if (c === this.t && !this.dirty) return;
    this.t = c;
    this.schedule();
  }

  schedule() {
    this.dirty = true;
    if (!this.frame) this.frame = requestAnimationFrame(this.tick);
  }

  tick(now) {
    this.frame = 0;
    if (this.playing) {
      const dt = this.last ? Math.min(0.1, (now - this.last) / 1000) : 0;
      this.last = now;
      // Seconds play at `speed` times model time; ticks play at `speed` x 10 ticks per second.
      const rate = this.unit === 'tick' ? 10 * this.speed : this.speed;
      let t = this.t + dt * rate;
      if (t >= this.t1) {
        t = this.t1;
        this.pause();
      }
      this.t = t;
      this.dirty = true;
    }
    if (this.dirty) {
      this.dirty = false;
      for (const fn of this.subs) fn(this.t);
    }
    if (this.playing) this.frame = requestAnimationFrame(this.tick);
  }

  play() {
    if (this.playing) return;
    if (this.t >= this.t1) this.t = this.t0;
    this.playing = true;
    this.last = 0;
    this.schedule();
    for (const fn of this.playSubs) fn(true);
  }

  pause() {
    if (!this.playing) return;
    this.playing = false;
    for (const fn of this.playSubs) fn(false);
  }

  toggle() {
    if (this.playing) this.pause();
    else this.play();
  }

  /** Moves by n recorded samples of the primary timebase. */
  step(n) {
    this.pause();
    const i = lowerIndex(this.samples, this.t);
    const exact = this.samples[i] === this.t;
    let j = n > 0 ? i + n : exact ? i + n : i + n + 1;
    j = Math.max(0, Math.min(this.samples.length - 1, j));
    this.set(this.samples[j]);
  }

  nextEvent() {
    this.pause();
    const t = this.eventTimes.find((x) => x > this.t + 1e-9);
    if (t !== undefined) this.set(t);
    return t;
  }

  prevEvent() {
    this.pause();
    const before = this.eventTimes.filter((x) => x < this.t - 1e-9);
    if (before.length) this.set(before[before.length - 1]);
    return before[before.length - 1];
  }

  dispose() {
    this.pause();
    if (this.frame) cancelAnimationFrame(this.frame);
    this.subs.clear();
    this.playSubs.clear();
  }
}
