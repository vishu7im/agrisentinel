import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {/* Outermost net. Individual panels are wrapped too, so a single panel failing costs that
        panel; this one only catches something that would otherwise blank the page. */}
    <ErrorBoundary label="AgriSentinel">
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
