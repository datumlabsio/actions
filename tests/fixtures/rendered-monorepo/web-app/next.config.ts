import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // A standalone build puts the server and only its needed dependencies in
  // .next/standalone, which is what goes in the container. DES §8: a web-app
  // deploys as a container, and a smaller image is a smaller attack surface.
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
