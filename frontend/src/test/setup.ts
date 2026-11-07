import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

window.scrollTo = vi.fn()
// Session restoration and lazy routes remain asynchronous under Windows load.
configure({ asyncUtilTimeout: 5000 })
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })
