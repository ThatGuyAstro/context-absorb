const state = {
  snapshot: null,
  counters: new Map(),
  eventSource: null,
  marqueeTween: null,
};

const els = {
  streamStatus: document.getElementById("streamStatus"),
  generatedAtLabel: document.getElementById("generatedAtLabel"),
  overlayAlias: document.getElementById("overlayAlias"),
  overlaySession: document.getElementById("overlaySession"),
  metricTotal: document.getElementById("metricTotal"),
  metricActive: document.getElementById("metricActive"),
  metricIdle: document.getElementById("metricIdle"),
  metricMissing: document.getElementById("metricMissing"),
  metricClaude: document.getElementById("metricClaude"),
  metricCodex: document.getElementById("metricCodex"),
  projectMarquee: document.getElementById("projectMarquee"),
  projectAccordion: document.getElementById("projectAccordion"),
  sessionStack: document.getElementById("sessionStack"),
  digestCommand: document.getElementById("digestCommand"),
  launchCommand: document.getElementById("launchCommand"),
  databasePath: document.getElementById("databasePath"),
  copyLaunchCommand: document.getElementById("copyLaunchCommand"),
  revealCopy: document.getElementById("revealCopy"),
};

function setStreamStatus(text) {
  if (els.streamStatus) {
    els.streamStatus.textContent = text;
  }
}

function numberTween(element, value) {
  if (!element || !window.gsap) {
    if (element) {
      element.textContent = String(value);
    }
    return;
  }
  const start = state.counters.get(element) ?? (Number(element.textContent) || 0);
  const holder = { value: start };
  window.gsap.to(holder, {
    value,
    duration: 0.9,
    ease: "power3.out",
    onUpdate: () => {
      element.textContent = String(Math.round(holder.value));
    },
  });
  state.counters.set(element, value);
}

function imageSeed(session) {
  return encodeURIComponent(`${session.cwd_label || "session"}-${session.source}-${session.state}`);
}

function renderMarquee(projects) {
  if (!els.projectMarquee) {
    return;
  }
  const chips = projects.length ? projects : [{ label: "No project data yet", session_count: 0 }];
  const repeated = chips.concat(chips);
  els.projectMarquee.innerHTML = repeated
    .map(
      (project) => `
        <span class="marquee-chip">${project.label} · ${project.active_count ?? 0} active · ${project.session_count} sessions</span>
      `
    )
    .join("");

  if (window.gsap) {
    if (state.marqueeTween) {
      state.marqueeTween.kill();
    }
    const width = els.projectMarquee.scrollWidth / 2;
    state.marqueeTween = window.gsap.fromTo(
      els.projectMarquee,
      { x: 0 },
      { x: -width, duration: 28, ease: "none", repeat: -1 }
    );
  }
}

function renderProjects(projects) {
  if (!els.projectAccordion) {
    return;
  }
  els.projectAccordion.innerHTML = projects
    .map(
      (project, index) => `
        <article
          class="project-card ${index === 0 ? "active" : ""}"
          style="--project-image: url('https://picsum.photos/seed/${encodeURIComponent(project.label)}/1200/800')"
        >
          <div class="metric-kicker">${project.sources.join(" + ")}</div>
          <h3>${project.label}</h3>
          <p>${project.cwd}</p>
          <div class="project-meta">
            <span class="project-pill">${project.active_count} active</span>
            <span class="project-pill">${project.session_count} tracked</span>
            <span class="project-pill">${project.latest_updated_label}</span>
          </div>
        </article>
      `
    )
    .join("");

  els.projectAccordion.querySelectorAll(".project-card").forEach((card) => {
    card.addEventListener("mouseenter", () => {
      els.projectAccordion.querySelectorAll(".project-card").forEach((node) => node.classList.remove("active"));
      card.classList.add("active");
    });
  });
}

function renderSessions(sessions) {
  if (!els.sessionStack) {
    return;
  }
  els.sessionStack.innerHTML = sessions
    .map(
      (session, index) => `
        <article class="session-card" data-state="${session.state}" data-index="${index}">
          <div class="session-card-head">
            <div class="session-title-wrap">
              <div class="session-meta">${session.source} · ${session.updated_label}</div>
              <h3 class="session-title">${session.title}</h3>
            </div>
            <div class="state-chip" data-state="${session.state}">${session.state}</div>
          </div>

          <div class="session-card-actions">
            <span class="source-chip">${session.alias_code || session.short_id}</span>
            <span class="source-chip">${session.cwd_label}</span>
            <span class="source-chip">${session.transcript_exists ? "transcript ready" : "no transcript"}</span>
          </div>

          <img
            class="session-card-image"
            src="https://picsum.photos/seed/${imageSeed(session)}/1200/700"
            alt="${session.cwd_label}"
          />

          <div class="session-meta-grid">
            <div class="session-meta-box">
              <span class="session-meta">Session id</span>
              <strong>${session.session_id}</strong>
            </div>
            <div class="session-meta-box">
              <span class="session-meta">Project root</span>
              <strong>${session.cwd || "unknown"}</strong>
            </div>
          </div>

          <div class="session-card-actions">
            <code class="session-command">${session.digest_command}</code>
            <code class="session-command">${session.launch_command}</code>
          </div>
        </article>
      `
    )
    .join("");

  if (window.gsap && window.ScrollTrigger) {
    window.gsap.utils.toArray(".session-card").forEach((card, index) => {
      window.gsap.fromTo(
        card,
        { y: 36, opacity: 0.2, scale: 0.94 },
        {
          y: 0,
          opacity: 1,
          scale: 1,
          duration: 0.7,
          ease: "power3.out",
          scrollTrigger: {
            trigger: card,
            start: "top 88%",
          },
          delay: Math.min(index * 0.03, 0.2),
        }
      );

      const image = card.querySelector(".session-card-image");
      if (image) {
        window.gsap.fromTo(
          image,
          { scale: 0.84, opacity: 0.36 },
          {
            scale: 1,
            opacity: 1,
            ease: "power2.out",
            scrollTrigger: {
              trigger: card,
              start: "top 82%",
              end: "bottom 18%",
              scrub: true,
            },
          }
        );
      }
    });
  }
}

function renderSnapshot(snapshot) {
  state.snapshot = snapshot;
  numberTween(els.metricTotal, snapshot.counts.total);
  numberTween(els.metricActive, snapshot.counts.active);
  numberTween(els.metricIdle, snapshot.counts.idle);
  numberTween(els.metricMissing, snapshot.counts.missing);
  numberTween(els.metricClaude, snapshot.by_source.claude.total);
  numberTween(els.metricCodex, snapshot.by_source.codex.total);

  const lead = snapshot.sessions[0];
  if (lead) {
    els.overlayAlias.textContent = lead.alias_code || lead.short_id;
    els.overlaySession.textContent = `${lead.title} · ${lead.cwd || "unknown cwd"}`;
    els.digestCommand.textContent = lead.digest_command;
    els.launchCommand.textContent = lead.launch_command;
  }

  els.generatedAtLabel.textContent = `Last snapshot · ${snapshot.generated_at_local}`;
  els.databasePath.textContent = `Catalog: ${snapshot.database_path}`;

  renderMarquee(snapshot.projects);
  renderProjects(snapshot.projects);
  renderSessions(snapshot.sessions);
}

async function fetchSnapshot() {
  const response = await fetch("/api/live?limit=60", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to fetch snapshot: ${response.status}`);
  }
  return response.json();
}

function startEventStream() {
  if (!window.EventSource) {
    setStreamStatus("polling");
    setInterval(async () => {
      try {
        renderSnapshot(await fetchSnapshot());
      } catch (_) {
        setStreamStatus("reconnecting");
      }
    }, 5000);
    return;
  }

  state.eventSource = new EventSource("/api/events?limit=60");
  state.eventSource.addEventListener("snapshot", (event) => {
    setStreamStatus("live");
    renderSnapshot(JSON.parse(event.data));
  });
  state.eventSource.onerror = async () => {
    setStreamStatus("reconnecting");
    try {
      renderSnapshot(await fetchSnapshot());
    } catch (_) {
      setStreamStatus("offline");
    }
  };
}

function splitRevealCopy() {
  if (!els.revealCopy) {
    return;
  }
  const words = els.revealCopy.textContent.trim().split(/\s+/);
  els.revealCopy.innerHTML = words
    .map((word) => `<span class="reveal-word">${word}</span>`)
    .join(" ");
}

function initMotion() {
  if (!window.gsap || !window.ScrollTrigger) {
    return;
  }

  window.gsap.registerPlugin(window.ScrollTrigger);

  window.gsap.from(".topbar-pill", {
    y: -28,
    opacity: 0,
    duration: 0.8,
    ease: "power3.out",
  });

  window.gsap.from(".hero-copy > *", {
    y: 36,
    opacity: 0,
    duration: 0.9,
    ease: "power3.out",
    stagger: 0.08,
  });

  window.gsap.from(".hero-media-frame", {
    y: 50,
    opacity: 0,
    scale: 0.92,
    duration: 1.1,
    ease: "power3.out",
  });

  window.ScrollTrigger.create({
    trigger: "#scrollNarrative",
    start: "top top+=12",
    end: "bottom bottom",
    pin: ".pin-copy",
    pinSpacing: false,
  });

  window.gsap.to(".reveal-word", {
    opacity: 1,
    ease: "none",
    stagger: 0.05,
    scrollTrigger: {
      trigger: "#scrollNarrative",
      start: "top 55%",
      end: "bottom 45%",
      scrub: true,
    },
  });
}

function bindCopyButton() {
  if (!els.copyLaunchCommand) {
    return;
  }
  els.copyLaunchCommand.addEventListener("click", async () => {
    const text = els.launchCommand.textContent || "session-absorb web --open-browser";
    try {
      await navigator.clipboard.writeText(text);
      els.copyLaunchCommand.textContent = "Copied command";
      window.setTimeout(() => {
        els.copyLaunchCommand.textContent = "Copy launch command";
      }, 1400);
    } catch (_) {
      els.copyLaunchCommand.textContent = "Clipboard blocked";
    }
  });
}

async function boot() {
  splitRevealCopy();
  bindCopyButton();
  initMotion();
  try {
    renderSnapshot(await fetchSnapshot());
    setStreamStatus("ready");
  } catch (_) {
    setStreamStatus("offline");
  }
  startEventStream();
}

window.addEventListener("DOMContentLoaded", boot);
