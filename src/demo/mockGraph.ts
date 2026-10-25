/**
 * Mock repository graph — ~19-file Express-style TypeScript app.
 * Represents an auth + routes + user model + services architecture.
 * Used for Demo Mode and as the primary demo scenario.
 */

import type { DependencyGraph, RepoMeta } from '../core/types';

export const MOCK_REPO: RepoMeta = {
  owner: 'acme-corp',
  repo: 'express-api',
  branch: 'main',
  sha: 'demo0000000000000000000000000000000000001',
};

export const MOCK_GRAPH: DependencyGraph = {
  'src/server.ts': {
    path: 'src/server.ts',
    imports: ['src/app.ts', 'src/config/index.ts'],
    dependents: [],
    summary: 'Entry point. Creates HTTP server on configured port.',
    exports: [],
  },
  'src/app.ts': {
    path: 'src/app.ts',
    imports: [
      'src/routes/index.ts',
      'src/middleware/errorHandler.ts',
      'src/config/index.ts',
    ],
    dependents: ['src/server.ts'],
    summary: 'Express app factory. Registers middleware, routes, and error handler. Exports: app.',
    exports: ['app'],
  },
  'src/config/index.ts': {
    path: 'src/config/index.ts',
    imports: [],
    dependents: [
      'src/server.ts',
      'src/app.ts',
      'src/services/authService.ts',
      'src/services/emailService.ts',
    ],
    summary: 'App config from env vars: PORT, JWT_SECRET, DB_URL, SMTP_HOST. Exports: config.',
    exports: ['config'],
  },
  'src/middleware/auth.ts': {
    path: 'src/middleware/auth.ts',
    imports: ['src/utils/jwt.ts', 'src/models/user.ts', 'src/types/index.ts'],
    dependents: [
      'src/routes/auth.ts',
      'src/routes/users.ts',
      'src/routes/posts.ts',
    ],
    summary: 'JWT authentication middleware. Verifies token, attaches user to req. Exports: authenticate, requireAuth.',
    exports: ['authenticate', 'requireAuth'],
  },
  'src/middleware/errorHandler.ts': {
    path: 'src/middleware/errorHandler.ts',
    imports: ['src/types/index.ts'],
    dependents: ['src/app.ts'],
    summary: 'Global Express error handler. Formats errors as JSON. Exports: errorHandler.',
    exports: ['errorHandler'],
  },
  'src/routes/index.ts': {
    path: 'src/routes/index.ts',
    imports: [
      'src/routes/auth.ts',
      'src/routes/users.ts',
      'src/routes/posts.ts',
    ],
    dependents: ['src/app.ts'],
    summary: 'Route aggregator. Mounts auth, users, posts routers at their prefix paths. Exports: router.',
    exports: ['router'],
  },
  'src/routes/auth.ts': {
    path: 'src/routes/auth.ts',
    imports: [
      'src/middleware/auth.ts',
      'src/services/authService.ts',
      'src/types/index.ts',
    ],
    dependents: ['src/routes/index.ts'],
    summary: 'Auth routes: POST /login, POST /register, POST /refresh, POST /logout. Exports: authRouter.',
    exports: ['authRouter'],
  },
  'src/routes/users.ts': {
    path: 'src/routes/users.ts',
    imports: [
      'src/middleware/auth.ts',
      'src/services/userService.ts',
      'src/types/index.ts',
    ],
    dependents: ['src/routes/index.ts'],
    summary: 'User CRUD routes: GET /users, GET /users/:id, PUT /users/:id, DELETE /users/:id. Exports: usersRouter.',
    exports: ['usersRouter'],
  },
  'src/routes/posts.ts': {
    path: 'src/routes/posts.ts',
    imports: [
      'src/middleware/auth.ts',
      'src/models/post.ts',
      'src/types/index.ts',
    ],
    dependents: ['src/routes/index.ts'],
    summary: 'Post routes: GET /posts, POST /posts, PUT /posts/:id, DELETE /posts/:id. Exports: postsRouter.',
    exports: ['postsRouter'],
  },
  'src/models/user.ts': {
    path: 'src/models/user.ts',
    imports: ['src/types/index.ts'],
    dependents: [
      'src/middleware/auth.ts',
      'src/services/authService.ts',
      'src/services/userService.ts',
      'src/models/post.ts',
      'tests/auth.test.ts',
      'tests/users.test.ts',
    ],
    summary: 'User model and DB schema. Fields: id, email, passwordHash, createdAt. Exports: User, UserSchema.',
    exports: ['User', 'UserSchema'],
  },
  'src/models/post.ts': {
    path: 'src/models/post.ts',
    imports: ['src/types/index.ts', 'src/models/user.ts'],
    dependents: ['src/routes/posts.ts'],
    summary: 'Post model and DB schema. Fields: id, title, content, authorId, createdAt. Exports: Post, PostSchema.',
    exports: ['Post', 'PostSchema'],
  },
  'src/services/authService.ts': {
    path: 'src/services/authService.ts',
    imports: [
      'src/utils/jwt.ts',
      'src/utils/hash.ts',
      'src/models/user.ts',
      'src/services/emailService.ts',
      'src/config/index.ts',
    ],
    dependents: ['src/routes/auth.ts', 'tests/auth.test.ts'],
    summary: 'Auth service: login(), register(), refreshToken(), logout(). Issues JWTs. Exports: AuthService.',
    exports: ['AuthService'],
  },
  'src/services/userService.ts': {
    path: 'src/services/userService.ts',
    imports: ['src/models/user.ts'],
    dependents: ['src/routes/users.ts', 'tests/users.test.ts'],
    summary: 'User service: getUser(), listUsers(), updateUser(), deleteUser(). Exports: UserService.',
    exports: ['UserService'],
  },
  'src/services/emailService.ts': {
    path: 'src/services/emailService.ts',
    imports: ['src/config/index.ts'],
    dependents: ['src/services/authService.ts'],
    summary: 'Email service via SMTP: sendWelcomeEmail(), sendPasswordReset(). Exports: EmailService.',
    exports: ['EmailService'],
  },
  'src/utils/jwt.ts': {
    path: 'src/utils/jwt.ts',
    imports: ['src/types/index.ts'],
    dependents: ['src/middleware/auth.ts', 'src/services/authService.ts'],
    summary: 'JWT utilities: signToken(), verifyToken(), decodeToken(). Exports: signToken, verifyToken, decodeToken.',
    exports: ['signToken', 'verifyToken', 'decodeToken'],
  },
  'src/utils/hash.ts': {
    path: 'src/utils/hash.ts',
    imports: [],
    dependents: ['src/services/authService.ts'],
    summary: 'Password hashing via bcrypt: hashPassword(), comparePassword(). Exports: hashPassword, comparePassword.',
    exports: ['hashPassword', 'comparePassword'],
  },
  'src/types/index.ts': {
    path: 'src/types/index.ts',
    imports: [],
    dependents: [
      'src/middleware/auth.ts',
      'src/middleware/errorHandler.ts',
      'src/routes/auth.ts',
      'src/routes/users.ts',
      'src/routes/posts.ts',
      'src/models/user.ts',
      'src/models/post.ts',
      'src/utils/jwt.ts',
    ],
    summary: 'Shared TypeScript types: User, Post, AuthPayload, ApiResponse, AppError. Exports: all.',
    exports: ['User', 'Post', 'AuthPayload', 'ApiResponse', 'AppError'],
  },
  'tests/auth.test.ts': {
    path: 'tests/auth.test.ts',
    imports: ['src/services/authService.ts', 'src/models/user.ts'],
    dependents: [],
    summary: 'Auth service unit tests: login, register, token refresh, and validation.',
    exports: [],
  },
  'tests/users.test.ts': {
    path: 'tests/users.test.ts',
    imports: ['src/services/userService.ts', 'src/models/user.ts'],
    dependents: [],
    summary: 'User service unit tests: CRUD operations and access control.',
    exports: [],
  },
};
