import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the container image.
  output: "standalone",
  // Monorepo: trace dependencies from the repository root.
  outputFileTracingRoot: path.join(__dirname, "../.."),
  poweredByHeader: false,
  // The typed API client is shipped as TypeScript source (IF-01).
  transpilePackages: ["@jude/contracts"],
};

export default nextConfig;
