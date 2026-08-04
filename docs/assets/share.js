"use strict";
window.NV = window.NV || {};

(function () {
  const share = {};

  // Canonical URL of the page being exported. The site is served from GitHub Pages under a
  // project path, so location.href is the only reliable source - there is no hardcoded domain.
  function pageUrl() {
    const config = (window.NV.app && window.NV.app.config) || {};
    if (config.siteUrl) {
      return config.siteUrl;
    }
    return location.origin + location.pathname;
  }

  // --- toMarkdown ---
  share.toMarkdown = function (payload, articles) {
    const day = payload.day || "";
    const dateObj = day ? new Date(day + "T00:00:00") : new Date();
    const dateStr = dateObj.toLocaleDateString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).replace(/\//g, "/"); // already DD/MM/YYYY
    const count = articles.length;
    let md = `# ${dateStr} — ${count} bài viết\n\n`;

    // Brief bullets
    if (payload.brief && payload.brief.length > 0) {
      md += "## Điểm chính\n\n";
      payload.brief.forEach((bullet) => {
        md += `- ${bullet}\n`;
      });
      md += "\n";
    }

    // Articles
    articles.forEach((art) => {
      const title = art.t || art.to || "Không có tiêu đề";
      const url = art.u || "";
      // Escape [ ] and backticks in title
      const escapedTitle = title.replace(/\[/g, "\\[").replace(/\]/g, "\\]").replace(/`/g, "\\`");
      md += `### [${escapedTitle}](${url})\n\n`;
      const source = art.s || "";
      const topic = art.tp || "";
      const score = art.sc != null ? art.sc : 0;
      md += `*Nguồn · ${source} · ${topic} · điểm ${score}*\n\n`;
      if (art.sum) {
        md += `${art.sum}\n\n`;
      }
      if (art.kp && art.kp.length > 0) {
        art.kp.forEach((point) => {
          md += `- ${point}\n`;
        });
        md += "\n";
      }
    });

    md += "---\n\n";
    md += `Nguồn: ${pageUrl()}\n`;
    return md;
  };

  // --- download ---
  share.download = function (filename, text, mime) {
    const blob = new Blob([text], { type: mime || "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    // Revoke on next tick
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  // --- copyText ---
  share.copyText = async function (text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (e) {
        // fall through
      }
    }
    // Fallback
    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.left = "-9999px";
      textarea.style.top = "-9999px";
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      const success = document.execCommand("copy");
      document.body.removeChild(textarea);
      return success;
    } catch (e) {
      return false;
    }
  };

  // --- printPage ---
  share.printPage = function () {
    window.print();
  };

  // --- cardPng ---
  share.cardPng = async function (article, options) {
    const width = 1200;
    const height = 630;
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");

    // Read theme colors from computed style with fallbacks
    const root = document.documentElement;
    const style = getComputedStyle(root);
    const bgColor = style.getPropertyValue("--card-bg").trim() || "#1a1a2e";
    const accentColor = style.getPropertyValue("--card-accent").trim() || "#e94560";
    const textColor = style.getPropertyValue("--card-text").trim() || "#ffffff";
    const mutedColor = style.getPropertyValue("--card-muted").trim() || "#a0a0b0";
    const siteColor = style.getPropertyValue("--card-site").trim() || "#888888";

    // Background
    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, width, height);

    // Accent bar
    ctx.fillStyle = accentColor;
    ctx.fillRect(0, 0, 8, height);

    // Title
    const title = article.t || article.to || "Không có tiêu đề";
    const maxWidth = width - 80;
    const lineHeight = 60;
    const maxLines = 5;
    const fontSize = 48;
    ctx.font = `bold ${fontSize}px system-ui, sans-serif`;
    ctx.fillStyle = textColor;
    ctx.textBaseline = "top";

    // Word wrap
    const words = title.split(/\s+/);
    let lines = [];
    let currentLine = "";
    for (let word of words) {
      const testLine = currentLine ? currentLine + " " + word : word;
      const metrics = ctx.measureText(testLine);
      if (metrics.width > maxWidth && currentLine) {
        lines.push(currentLine);
        currentLine = word;
        if (lines.length >= maxLines) break;
      } else {
        currentLine = testLine;
      }
    }
    if (currentLine && lines.length < maxLines) {
      lines.push(currentLine);
    }
    // If still too many lines, truncate last line
    if (lines.length > maxLines) {
      lines = lines.slice(0, maxLines);
      // Add ellipsis to last line
      let last = lines[maxLines - 1];
      while (ctx.measureText(last + "…").width > maxWidth && last.length > 0) {
        last = last.slice(0, -1);
      }
      lines[maxLines - 1] = last + "…";
    }

    const startY = 60;
    lines.forEach((line, i) => {
      ctx.fillText(line, 40, startY + i * lineHeight);
    });

    // Source and score
    const source = article.s || "";
    const score = article.sc != null ? article.sc : 0;
    ctx.font = `24px system-ui, sans-serif`;
    ctx.fillStyle = mutedColor;
    const sourceY = height - 80;
    ctx.fillText(`${source} · điểm ${score}`, 40, sourceY);

    // Site name in corner
    ctx.font = `20px system-ui, sans-serif`;
    ctx.fillStyle = siteColor;
    ctx.textAlign = "right";
    ctx.textBaseline = "bottom";
    ctx.fillText("Kho tin", width - 40, height - 20);

    // Reset text align
    ctx.textAlign = "start";
    ctx.textBaseline = "top";

    // Convert to blob
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("Canvas toBlob failed"));
      }, "image/png");
    });
  };

  // --- telegramUrl ---
  share.telegramUrl = function (pageUrl, text) {
    const url = encodeURIComponent(pageUrl);
    const txt = encodeURIComponent(text);
    return `https://t.me/share/url?url=${url}&text=${txt}`;
  };

  NV.share = share;
})();
