const TOKEN_PATTERN = /(\[doc_\d+#p\d+\]|\*\*[^*]+\*\*|\*[^*]+\*)/g

function parseBlocks(markdown) {
  const lines = markdown.split('\n')
  const blocks = []

  for (let index = 0; index < lines.length;) {
    const line = lines[index].trim()
    if (!line) {
      index += 1
      continue
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/)
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, text: heading[2] })
      index += 1
      continue
    }

    const unordered = line.match(/^[-*]\s+(.+)$/)
    const ordered = line.match(/^\d+\.\s+(.+)$/)
    if (unordered || ordered) {
      const type = ordered ? 'ordered-list' : 'unordered-list'
      const matcher = ordered ? /^\d+\.\s+(.+)$/ : /^[-*]\s+(.+)$/
      const items = []
      while (index < lines.length) {
        const item = lines[index].trim().match(matcher)
        if (!item) break
        items.push(item[1])
        index += 1
      }
      blocks.push({ type, items })
      continue
    }

    const paragraph = []
    while (index < lines.length) {
      const candidate = lines[index].trim()
      if (!candidate || /^(#{1,3})\s+/.test(candidate) || /^([-*]\s+|\d+\.\s+)/.test(candidate)) break
      paragraph.push(candidate)
      index += 1
    }
    blocks.push({ type: 'paragraph', text: paragraph.join(' ') })
  }

  return blocks
}

function InlineContent({ onSource, sourceNumbers, text }) {
  return text.split(TOKEN_PATTERN).filter(Boolean).map((token, index) => {
    const marker = token.match(/^\[(doc_\d+#p\d+)\]$/)
    if (marker) {
      const sourceEntry = sourceNumbers.get(marker[1])
      return (
        <button
          aria-label={sourceEntry ? `Open source ${sourceEntry.number}` : `Source ${marker[1]} unavailable`}
          className="mx-1 inline-flex min-w-6 -translate-y-px items-center justify-center rounded-full border border-emerald-400/30 bg-emerald-400/10 px-1.5 py-0.5 text-[10px] font-bold text-emerald-300 transition hover:border-emerald-300 hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:border-slate-700 disabled:bg-slate-800 disabled:text-slate-500"
          disabled={!sourceEntry}
          key={`${token}-${index}`}
          onClick={() => sourceEntry && onSource(sourceEntry.source)}
          title={sourceEntry ? `${sourceEntry.source.doc}, page ${sourceEntry.source.page}` : marker[1]}
          type="button"
        >
          {sourceEntry?.number ?? '?'}
        </button>
      )
    }
    if (token.startsWith('**')) return <strong key={`${token}-${index}`}>{token.slice(2, -2)}</strong>
    if (token.startsWith('*')) return <em key={`${token}-${index}`}>{token.slice(1, -1)}</em>
    return token
  })
}

export default function MarkdownPlan({ markdown, onSource, sourceNumbers }) {
  const blocks = parseBlocks(markdown)
  const inline = (text) => <InlineContent onSource={onSource} sourceNumbers={sourceNumbers} text={text} />

  return (
    <div className="space-y-4 text-base leading-7 text-slate-300">
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          return <h3 className="border-b border-field-border pb-2 pt-2 text-lg font-semibold text-white" key={`${block.text}-${index}`}>{inline(block.text)}</h3>
        }
        if (block.type.endsWith('list')) {
          const List = block.type === 'ordered-list' ? 'ol' : 'ul'
          return <List className={`space-y-2 pl-6 ${List === 'ol' ? 'list-decimal' : 'list-disc'}`} key={`list-${index}`}>{block.items.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{inline(item)}</li>)}</List>
        }
        return <p key={`${block.text}-${index}`}>{inline(block.text)}</p>
      })}
    </div>
  )
}
