module.exports = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/setupTests.ts"],
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json"],
  transform: {
    "^.+\\.(ts|tsx)$": [
      "ts-jest",
      {
        tsconfig: {
          jsx: "react-jsx",
          esModuleInterop: true,
          module: "commonjs",
          moduleResolution: "node",
          isolatedModules: true,
        },
      },
    ],
  },
  testMatch: ["**/__tests__/**/*.[jt]s?(x)", "**/?(*.)+(test).[jt]s?(x)"],
  testPathIgnorePatterns: ["/node_modules/", "/.next/", "/tests/e2e/"],
  moduleNameMapper: {
    "\\.(css|less|scss)$": "<rootDir>/tests/styleMock.js",
  },
  collectCoverage: false,
  collectCoverageFrom: ["components/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}", "pages/candidate-*.tsx"],
  coverageDirectory: "<rootDir>/coverage",
};
