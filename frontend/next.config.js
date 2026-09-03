/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    return [
      { source: "/api/:path*", destination: "http://localhost:8100/api/:path*" },
    ];
  },
};
module.exports = nextConfig;
