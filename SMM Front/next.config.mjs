/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // 开发时把 /api 和 /health 代理到后端，避免跨域
  async rewrites() {
    const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"
    return [
      { source: "/api/:path*", destination: `${base}/api/:path*` },
      { source: "/health", destination: `${base}/health` },
    ]
  },
}

export default nextConfig
