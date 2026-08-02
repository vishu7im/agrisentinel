const LINKS = [
  { href: '#field-scan', icon: '⌖', label: 'Field' },
  { href: '#agent-activity', icon: '◌', label: 'Live' },
  { href: '#field-actions', icon: '✓', label: 'Brief' },
  { href: '#treatment-plan', icon: '≡', label: 'Plan' },
]

export default function MobileFieldNav({ phase }) {
  const busy = phase === 'uploading' || phase === 'scanning'

  return (
    <nav className="mobile-field-nav lg:hidden" aria-label="Field workflow">
      <div className="mx-auto grid max-w-lg grid-cols-4">
        {LINKS.map((link) => (
          <a
            className="relative flex min-h-14 flex-col items-center justify-center gap-0.5 rounded-lg text-[10px] font-semibold text-slate-400 transition hover:bg-white/5 hover:text-white"
            href={link.href}
            key={link.href}
          >
            <span aria-hidden="true" className="text-base leading-none text-emerald-300">{link.icon}</span>
            {link.label}
            {busy && link.href === '#agent-activity' && (
              <span className="absolute right-[28%] top-2 size-1.5 animate-pulse rounded-full bg-cyan-300" />
            )}
          </a>
        ))}
      </div>
    </nav>
  )
}
