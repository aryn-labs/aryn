import { Link } from '@tanstack/react-router'
import arynLogo from '@/assets/aryn-logo.png'

export function Brand() {
  return (
    <Link to="/" className="brand" aria-label="ARYN Studio home">
      {/* Keep the supplied artwork intact; frame its two parts for a compact horizontal lockup. */}
      <span className="brand-symbol" aria-hidden="true">
        <img src={arynLogo} alt="" width={858} height={707} />
      </span>
      <span className="brand-wordmark" aria-hidden="true">
        <img src={arynLogo} alt="" width={858} height={707} />
      </span>
    </Link>
  )
}
