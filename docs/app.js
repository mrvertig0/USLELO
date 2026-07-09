(function () {
  "use strict";

  var boardBody = document.getElementById("board-body");
  var searchInput = document.getElementById("search");
  var metaLine = document.getElementById("meta-line");
  var footerUpdated = document.getElementById("footer-updated");
  var heroNum = document.getElementById("hero-num");
  var heroTeamName = document.getElementById("hero-team-name");
  var heroTeamRecord = document.getElementById("hero-team-record");

  var allTeams = [];
  var historyByTeam = {};

  function fmtDate(iso) {
    if (!iso) return "unknown";
    var d = new Date(iso);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) +
      " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }

  function sparkline(points) {
    // points: array of {t, rating}. Build a tiny inline SVG trend line.
    var vals = points.map(function (p) { return p.rating; });
    if (vals.length < 2) return "";
    var w = 72, h = 26, pad = 3;
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
    var stroke = trendUp ? "var(--up)" : "var(--down)";
    var last3 = vals.slice(-3);
    return (
      '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h + '" ' +
      'preserveAspectRatio="none" role="img" aria-label="rating trend">' +
      '<polyline fill="none" stroke="' + stroke + '" stroke-width="1.6" ' +
      'stroke-linecap="round" stroke-linejoin="round" points="' + coords.join(" ") + '"/>' +
      "</svg>"
    );
  }

  function renderRow(team) {
    var tr = document.createElement("tr");
    var hist = historyByTeam[String(team.team_id)] || [];
    tr.innerHTML =
      '<td class="col-rank">' + team.rank + "</td>" +
      '<td class="col-team">' + escapeHtml(team.team) + "</td>" +
      '<td class="col-form">' + sparkline(hist) + "</td>" +
      '<td class="col-rating">' + team.rating.toFixed(1) + "</td>" +
      '<td class="col-record">' + team.games_played + "</td>" +
      '<td class="col-record">' + team.wins + "</td>" +
      '<td class="col-record">' + team.draws + "</td>" +
      '<td class="col-record">' + team.losses + "</td>";
    tr.dataset.name = team.team.toLowerCase();
    return tr;
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function renderBoard(teams) {
    boardBody.innerHTML = "";
    if (!teams.length) {
      boardBody.innerHTML = '<tr><td colspan="8" class="empty-row">No clubs match that search.</td></tr>';
      return;
    }
    var frag = document.createDocumentFragment();
    teams.forEach(function (t) { frag.appendChild(renderRow(t)); });
    boardBody.appendChild(frag);
  }

  function applyFilter() {
    var q = searchInput.value.trim().toLowerCase();
    if (!q) { renderBoard(allTeams); return; }
    renderBoard(allTeams.filter(function (t) { return t.team.toLowerCase().indexOf(q) !== -1; }));
  }

  searchInput.addEventListener("input", applyFilter);

  Promise.all([
    fetch("data/ratings.json").then(function (r) {
      if (!r.ok) throw new Error("ratings.json " + r.status);
      return r.json();
    }),
    fetch("data/history.json").then(function (r) {
      if (!r.ok) throw new Error("history.json " + r.status);
      return r.json();
    }).catch(function () { return {}; }),
  ])
    .then(function (results) {
      var ratings = results[0];
      historyByTeam = results[1] || {};
      allTeams = ratings.teams || [];

      metaLine.textContent = allTeams.length + " clubs \u00b7 " + ratings.matches_used + " matches played";
      footerUpdated.textContent = "ratings last computed " + fmtDate(ratings.generated_at_utc) +
        (ratings.data_fetched_at_utc ? " \u00b7 data pulled " + fmtDate(ratings.data_fetched_at_utc) : "");

      if (allTeams.length) {
        var top = allTeams[0];
        heroNum.textContent = top.rating.toFixed(0);
        heroTeamName.textContent = top.team;
        heroTeamRecord.textContent = top.wins + "W " + top.draws + "D " + top.losses + "L";
      }

      renderBoard(allTeams);
    })
    .catch(function (err) {
      boardBody.innerHTML =
        '<tr><td colspan="8" class="empty-row">Couldn\u2019t load ratings data (' +
        escapeHtml(err.message) + "). If this is a fresh setup, run the fetch + compute " +
        "scripts once and commit docs/data/*.json.</td></tr>";
      heroTeamName.textContent = "No data yet";
    });
})();
