import { PHASE_DEVELOPMENT_SERVER } from "next/constants.js"

export default (phase) => {
  const isDevServer = phase === PHASE_DEVELOPMENT_SERVER
  return {
    reactStrictMode: true,
    distDir: isDevServer ? ".next-dev" : ".next"
  }
}
