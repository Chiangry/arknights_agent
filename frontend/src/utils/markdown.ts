import MarkdownIt from 'markdown-it'

// html:false 转义原始 HTML，避免 LLM 输出带来的 XSS；breaks 把换行转成 <br>
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  typographer: false,
})

// 引用跳转等所有外部链接都在新标签页打开，且不向目标页泄露本页来源
const defaultRender =
  md.renderer.rules.link_open ||
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultRender(tokens, idx, options, env, self)
}

export function renderMarkdown(src: string): string {
  return md.render(src || '')
}
