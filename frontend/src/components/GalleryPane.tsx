export function GalleryPane() {
  return (
    <section className="gallery-pane" data-pane="gallery" aria-label="风格图库">
      <header className="gallery-heading">
        <div>
          <p className="pane-kicker">LOOKS</p>
          <h2>风格图库</h2>
        </div>
        <nav aria-label="图库来源">
          <button type="button" aria-pressed="true" disabled>内置模板</button>
          <button type="button" aria-pressed="false" disabled>我的风格</button>
        </nav>
      </header>
      <div className="contact-sheet" aria-label="风格卡片占位">
        {["自然", "青橙", "胶片", "日系"].map((name) => (
          <button className="look-placeholder" type="button" key={name} disabled>
            <span />
            <strong>{name}</strong>
          </button>
        ))}
      </div>
    </section>
  );
}
