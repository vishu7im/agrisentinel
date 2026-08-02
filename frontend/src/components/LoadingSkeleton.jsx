export function SkeletonBlock({ className = '' }) {
  return <span aria-hidden="true" className={`skeleton-block block rounded-md ${className}`} />
}

export default function LoadingSkeleton({ children, className = '', label }) {
  return (
    <div aria-busy="true" className={className} role="status">
      <span className="sr-only">{label}</span>
      {children}
    </div>
  )
}
