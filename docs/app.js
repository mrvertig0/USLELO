(function () {
  "use strict";

  var boardBody = document.getElementById("board-body");
  var searchInput = document.getElementById("search");
  var metaLine = document.getElementById("meta-line");
  var footerUpdated = document.getElementById("footer-updated");
  var heroNum = document.getElementById("hero-num");
  var heroTeamName = document.getElementById("hero-team-name");
  var heroTeamRecord = document.getElementById("hero-team-record");
  var heroNote = document.getElementById("hero-note");
  var leagueTabs = document.getElementById("league-tabs");
  var seasonToggle = document.getElementById("season-toggle");
  var moversSection = document.getElementById("movers-section");
  var moversUp = document.getElementById("movers-up");
  var moversDown = document.getElementById("movers-down");
  var modalOverlay = document.getElementById("modal-overlay");
  var modalClose = document.getElementById("modal-close");
  var modalTeamName = document.getElementById("modal-team-name");
  var modalTeamSub = document.getElementById("modal-team-sub");
  var modalChartWrap = document.getElementById("modal-chart-wrap");

  var LEAGUES = {
    usl2: {
      label: "USL League Two",
      allTimeNote: "Every result since the league's post-PDL rebrand, folded into one running rating. Recalculated after every update.",
    },
    wleague: {
      label: "USL W League",
      allTimeNote: "Every result since the league launched, folded into one running rating. Recalculated after every update.",
    },
  };

  // datasets[league][scope] = { ratings, teams, history }
  var datasets = { usl2: {}, wleague: {} };
  var activeLeague = "usl2";
  var activeScope = "all_time";

  function fmtDate(iso) {
    if (!iso) return "unknown";
    var d = new Date(iso);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) +
      " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function buildSvgPath(points, w, h, pad) {
    var vals = points.map(function (p) { return p.rating; });
    if (vals.length < 2) return null;
    var min = Math.min.apply(null, vals);
    var max = Math.max.apply(null, vals);
    var range = max - min || 1;
    var last = vals.length - 1;
    var coords = vals.map(function (v, i) {
      var x = pad + (i / last) * (w - 2 * pad);
      var y = h - pad - ((v - min) / range) * (h - 2 * pad);
      return x.toFixed(1) + "," + y.toFixed(1);
    });
    var trendUp = vals[vals.length - 1] >= vals[0];
    return { coords: coords.join(" "), trendUp: trendUp };
  }

  function sparkline(points) {
    var w = 72, h = 26, pad = 3;
    var built = buildSvgPath(points, w, h, pad);
    if (!built) return "";
    var stroke = built.trendUp ? "var(--up)" : "var(--down)";
    return (
      '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h + '" ' +
      'preserveAspectRatio="none" role="img" aria-label="rating trend">' +
      '<polyline fill="none" stroke="' + stroke + '" stroke-width="1.6" ' +
      'stroke-linecap="round" stroke-linejoin="round" points="' + built.coords + '"/>' +
      "</svg>"
    );
  }

  function bigChart(points) {
    var w = 640, h = 260, pad = 28;
    var built = buildSvgPath(points, w, h, pad);
    if (!built) {
      return '<p class="modal-empty">Not enough matches yet for a chart.</p>';
    }
    var vals = points.map(function (p) { return p.rating; });
    var min = Math.min.apply(null, vals);
    var max = Math.max.apply(null, vals);
    var stroke = built.trendUp ? "var(--up)" : "var(--down)";

    var mid = (min + max) / 2;
    var gridVals = [min, mid, max];
    var gridLines = gridVals.map(function (v) {
      var y = h - pad - ((v - min) / (max - min || 1)) * (h - 2 * pad);
      return (
        '<line x1="' + pad + '" y1="' + y.toFixed(1) + '" x2="' + (w - pad) + '" y2="' + y.toFixed(1) + '" ' +
        'stroke="rgba(20,35,29,0.1)" stroke-width="1"/>' +
        '<text x="' + (pad - 6) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end" ' +
        'font-family="var(--mono)" font-size="11" fill="rgba(20,35,29,0.5)">' + v.toFixed(0) + "</text>"
      );
    }).join("");

    var firstDate = points[1] && points[1].t ? new Date(points[1].t * 1000) : null;
    var lastPoint = points[points.length - 1];
    var lastDate = lastPoint && lastPoint.t ? new Date(lastPoint.t * 1000) : null;
    var dateLabels = "";
    if (firstDate && lastDate) {
      dateLabels =
        '<text x="' + pad + '" y="' + (h - 6) + '" font-family="var(--mono)" font-size="11" ' +
        'fill="rgba(20,35,29,0.5)">' + firstDate.toLocaleDateString(undefined, { year: "numeric", month: "short" }) + "</text>" +
        '<text x="' + (w - pad) + '" y="' + (h - 6) + '" text-anchor="end" font-family="var(--mono)" font-size="11" ' +
        'fill="rgba(20,35,29,0.5)">' + lastDate.toLocaleDateString(undefined, { year: "numeric", month: "short" }) + "</text>";
    }

    return (
      '<svg width="100%" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Full rating history">' +
      gridLines +
      '<polyline fill="none" stroke="' + stroke + '" stroke-width="2.2" ' +
      'stroke-linecap="round" stroke-linejoin="round" points="' + built.coords + '"/>' +
      dateLabels +
      "</svg>"
    );
  }

  function openModal(team, history) {
    modalTeamName.textContent = team.team;
    modalTeamSub.textContent = team.wins + "W " + team.draws + "D " + team.losses + "L \u00b7 " +
      team.games_played + " matches \u00b7 current rating " + team.rating.toFixed(1);
    modalChartWrap.innerHTML = bigChart(history);
    modalOverlay.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    modalOverlay.hidden = true;
    document.body.style.overflow = "";
  }

  modalClose.addEventListener("click", closeModal);
  modalOverlay.addEventListener("click", function (e) {
    if (e.target === modalOverlay) closeModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modalOverlay.hidden) closeModal();
  });

  function renderRow(team, historyByTeam) {
    var tr = document.createElement("tr");
    var hist = historyByTeam[String(team.team_id)] || [];
    tr.innerHTML =
      '<td class="col-rank">' + team.rank + "</td>" +
      '<td class="col-team">' + escapeHtml(team.team) + "</td>" +
      '<td class="col-form"><button type="button" class="spark-btn" aria-label="View full rating history for ' +
        escapeHtml(team.team) + '">' + sparkline(hist) + "</button></td>" +
      '<td class="col-rating">' + team.rating.toFixed(1) + "</td>" +
      '<td class="col-record">' + team.games_played + "</td>" +
      '<td class="col-record">' + team.wins + "</td>" +
      '<td class="col-record">' + team.draws + "</td>" +
      '<td class="col-record">' + team.losses + "</td>";
    tr.dataset.name = team.team.toLowerCase();
    tr.querySelector(".spark-btn").addEventListener("click", function () {
      openModal(team, hist);
    });
    return tr;
  }

  function renderBoard(teams, historyByTeam) {
    boardBody.innerHTML = "";
    if (!teams.length) {
      boardBody.innerHTML = '<tr><td colspan="8" class="empty-row">No clubs match that search.</td></tr>';
      return;
    }
    var frag = document.createDocumentFragment();
    teams.forEach(function (t) { frag.appendChild(renderRow(t, historyByTeam)); });
    boardBody.appendChild(frag);
  }

  function renderMovers(teams) {
    var eligible = teams.filter(function (t) { return t.delta_recent_games >= 2; });
    var up = eligible.slice().sort(function (a, b) { return b.delta_recent - a.delta_recent; }).slice(0, 5)
      .filter(function (t) { return t.delta_recent > 0; });
    var down = eligible.slice().sort(function (a, b) { return a.delta_recent - b.delta_recent; }).slice(0, 5)
      .filter(function (t) { return t.delta_recent < 0; });

    if (!up.length && !down.length) {
      moversSection.hidden = true;
      return;
    }
    moversSection.hidden = false;

    function renderList(el, list, sign) {
      el.innerHTML = "";
      if (!list.length) {
        el.innerHTML = '<li class="movers-empty">Not enough recent matches yet.</li>';
        return;
      }
      list.forEach(function (t) {
        var li = document.createElement("li");
        li.className = "movers-item";
        var deltaStr = (sign > 0 ? "+" : "") + t.delta_recent.toFixed(1);
        li.innerHTML =
          '<span class="movers-name">' + escapeHtml(t.team) + "</span>" +
          '<span class="movers-delta ' + (sign > 0 ? "up" : "down") + '">' + deltaStr + "</span>";
        el.appendChild(li);
      });
    }

    renderList(moversUp, up, 1);
    renderList(moversDown, down, -1);
  }

  function applyFilter() {
    var ds = datasets[activeLeague][activeScope];
    if (!ds) return;
    var q = searchInput.value.trim().toLowerCase();
    var teams = q ? ds.teams.filter(function (t) { return t.team.toLowerCase().indexOf(q) !== -1; }) : ds.teams;
    renderBoard(teams, ds.history);
  }

  searchInput.addEventListener("input", applyFilter);

  function render() {
    var ds = datasets[activeLeague][activeScope];
    if (!ds) {
      boardBody.innerHTML = '<tr><td colspan="8" class="empty-row">No data yet for this view.</td></tr>';
      metaLine.textContent = "";
      heroTeamName.textContent = "No data yet";
      heroNum.textContent = "\u2014";
      moversSection.hidden = true;
      return;
    }

    metaLine.textContent = ds.teams.length + " clubs \u00b7 " + ds.ratings.matches_used + " matches" +
      (activeScope === "season" && ds.ratings.season_year ? " \u00b7 " + ds.ratings.season_year + " season" : " \u00b7 all-time");
    footerUpdated.textContent = "ratings last computed " + fmtDate(ds.ratings.generated_at_utc) +
      (ds.ratings.data_fetched_at_utc ? " \u00b7 data pulled " + fmtDate(ds.ratings.data_fetched_at_utc) : "");

    if (ds.teams.length) {
      var top = ds.teams[0];
      heroNum.textContent = top.rating.toFixed(0);
      heroTeamName.textContent = top.team;
      heroTeamRecord.textContent = top.wins + "W " + top.draws + "D " + top.losses + "L";
    }

    heroNote.textContent = activeScope === "season"
      ? "Reset to a level field at the start of " + (ds.ratings.season_year || "this season") + " and rebuilt from just this season's results."
      : LEAGUES[activeLeague].allTimeNote;

    renderMovers(ds.teams);
    applyFilter();
  }

  leagueTabs.addEventListener("click", function (e) {
    var btn = e.target.closest(".league-tab");
    if (!btn) return;
    var league = btn.dataset.league;
    if (league === activeLeague) return;
    activeLeague = league;
    Array.prototype.forEach.call(leagueTabs.querySelectorAll(".league-tab"), function (b) {
      b.classList.toggle("is-active", b === btn);
      b.setAttribute("aria-selected", b === btn ? "true" : "false");
    });
    render();
  });

  seasonToggle.addEventListener("click", function (e) {
    var btn = e.target.closest(".seg-btn");
    if (!btn) return;
    var scope = btn.dataset.scope;
    activeScope = scope;
    Array.prototype.forEach.call(seasonToggle.querySelectorAll(".seg-btn"), function (b) {
      b.classList.toggle("is-active", b === btn);
      b.setAttribute("aria-selected", b === btn ? "true" : "false");
    });
    render();
  });

  function loadJson(path) {
    return fetch(path).then(function (r) {
      if (!r.ok) throw new Error(path + " " + r.status);
      return r.json();
    });
  }

  function loadLeague(key) {
    return Promise.all([
      loadJson("data/ratings_" + key + ".json").catch(function () { return null; }),
      loadJson("data/history_" + key + ".json").catch(function () { return {}; }),
      loadJson("data/ratings_" + key + "_season.json").catch(function () { return null; }),
      loadJson("data/history_" + key + "_season.json").catch(function () { return {}; }),
    ]).then(function (r) {
      if (r[0]) datasets[key].all_time = { ratings: r[0], teams: r[0].teams || [], history: r[1] || {} };
      if (r[2]) datasets[key].season = { ratings: r[2], teams: r[2].teams || [], history: r[3] || {} };
    });
  }

  Promise.all([loadLeague("usl2"), loadLeague("wleague")])
    .then(function () {
      render();
    })
    .catch(function (err) {
      boardBody.innerHTML =
        '<tr><td colspan="8" class="empty-row">Couldn\u2019t load ratings data (' +
        escapeHtml(err.message) + "). If this is a fresh setup, run the fetch + compute " +
        "scripts once and commit docs/data/*.json.</td></tr>";
      heroTeamName.textContent = "No data yet";
    });
})();
