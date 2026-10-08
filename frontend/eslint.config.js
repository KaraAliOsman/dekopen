export default [
  // Approved toolchain: ESLint checks JS; strict tsc in `npm run lint` checks TS/TSX.
  // No unapproved TypeScript parser dependency is introduced.
  {
    ignores: [
      "dist/**",
      "test-results/**",
      "playwright-report/**",
      "src/**/*.ts",
      "src/**/*.tsx",
      "scripts/**/*.ts",
      "orval.config.ts",
      "vite.config.ts",
      "tailwind.config.ts",
    ],
  },
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        document: "readonly",
      },
      parserOptions: {
        ecmaFeatures: {
          jsx: true,
        },
      },
    },
    linterOptions: {
      reportUnusedDisableDirectives: true,
    },
    rules: {
      "no-undef": "error",
      "no-unused-vars": "error",
    },
  },
];
