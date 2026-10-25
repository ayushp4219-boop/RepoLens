/**
 * Mocked AI impact response for the primary demo scenario:
 * "Add role-based access control" on the MOCK_GRAPH repository.
 *
 * All paths exist in MOCK_GRAPH; no hallucinated files.
 */

import type { ImpactResponse } from '../core/types';

export const DEMO_CHANGE_REQUEST = 'Add role-based access control';

export const MOCK_IMPACT: ImpactResponse = {
  summary:
    'Adding RBAC to this Express API requires coordinated changes across 8 core files. ' +
    'The auth middleware needs a role-checking guard factory, the User model must gain a ' +
    'role field, and protected routes need explicit role guards. ' +
    'JWTs must carry the role so auth middleware can enforce it without a DB call on every request. ' +
    'Expect all existing sessions to be invalidated when the role field lands.',

  affectedFiles: [
    {
      path: 'src/middleware/auth.ts',
      impact: 'high',
      reason:
        'Central auth middleware controls all route protection. ' +
        'It must be extended with a requireRole() guard factory that reads req.user.role ' +
        'and either calls next() or responds 403 Forbidden.',
      recommendedChange:
        'Add `requireRole(...roles: Role[]) => RequestHandler` as a named export. ' +
        'Update the AuthPayload type it reads from the decoded JWT to include the role field.',
    },
    {
      path: 'src/models/user.ts',
      impact: 'high',
      reason:
        'The User schema has no role field. RBAC cannot function without persisting ' +
        'each user\'s role in the database.',
      recommendedChange:
        'Add `role: Role` (default: "user") to UserSchema and to the User TypeScript interface. ' +
        'Create a DB migration that back-fills existing users with role = "user".',
    },
    {
      path: 'src/types/index.ts',
      impact: 'high',
      reason:
        'The Role union type and updated User/AuthPayload interfaces must be defined here ' +
        'to ensure type safety across all files that import from this module.',
      recommendedChange:
        'Add `export type Role = "admin" | "moderator" | "user";` and update the User interface ' +
        'and AuthPayload to include `role: Role`.',
    },
    {
      path: 'src/utils/jwt.ts',
      impact: 'high',
      reason:
        'JWTs must encode the user\'s role so auth middleware can enforce roles ' +
        'without a database lookup on every request.',
      recommendedChange:
        'Include `role: Role` in the JWT payload passed to signToken(). ' +
        'Update the return type of verifyToken() to expose the role field in the decoded payload.',
    },
    {
      path: 'src/routes/users.ts',
      impact: 'medium',
      reason:
        'GET /users (list all users) and DELETE /users/:id are sensitive admin operations ' +
        'that currently have no role gate beyond authentication.',
      recommendedChange:
        'Wrap GET /users and DELETE /users/:id with `requireRole("admin")` middleware. ' +
        'Consider adding an admin-only PUT /users/:id/role endpoint for role assignment.',
    },
    {
      path: 'src/routes/posts.ts',
      impact: 'medium',
      reason:
        'Delete and moderation actions on posts should be restricted to moderators and admins ' +
        'to prevent regular users from removing others\' content.',
      recommendedChange:
        'Add `requireRole("moderator", "admin")` to DELETE /posts/:id. ' +
        'If a moderation endpoint exists or is planned, protect it similarly.',
    },
    {
      path: 'src/services/authService.ts',
      impact: 'medium',
      reason:
        'The register() function must assign a default role to new accounts. ' +
        'A privileged assignRole() method is also needed for admin tooling.',
      recommendedChange:
        'Set `role: "user"` as default in register(). ' +
        'Add `assignRole(userId: string, role: Role): Promise<User>` with admin validation. ' +
        'Ensure the signed JWT includes the role.',
    },
    {
      path: 'src/services/userService.ts',
      impact: 'low',
      reason:
        'listUsers() should support optional role filtering. ' +
        'updateUser() must block callers from self-escalating their own role.',
      recommendedChange:
        'Add an optional `role?: Role` filter param to listUsers(). ' +
        'In updateUser(), reject any request that attempts to change the role field ' +
        'unless the calling user is an admin.',
    },
  ],

  dependencyPaths: [
    {
      path: [
        'src/routes/users.ts',
        'src/middleware/auth.ts',
        'src/models/user.ts',
      ],
      reason:
        'Users route calls requireRole() from auth middleware, which reads the role ' +
        'from the User model — all three must be updated together for role guards to work.',
    },
    {
      path: [
        'src/services/authService.ts',
        'src/utils/jwt.ts',
        'src/middleware/auth.ts',
      ],
      reason:
        'Auth service signs tokens via JWT utils; auth middleware verifies them. ' +
        'The role field must flow through this entire chain without gaps.',
    },
    {
      path: [
        'src/types/index.ts',
        'src/models/user.ts',
        'src/middleware/auth.ts',
        'src/routes/users.ts',
      ],
      reason:
        'The Role type defined in types feeds into the User model, ' +
        'is read by auth middleware, and enforced at the route layer — ' +
        'a TypeScript change here ripples through all four files.',
    },
  ],

  testsToUpdate: ['tests/auth.test.ts', 'tests/users.test.ts'],

  risks: [
    'Breaking change: all existing JWTs will be invalid when the role field is added — users must re-login after deploy.',
    'Default role assignment must be atomic with user creation to prevent role-less users reaching the database.',
    'listUsers() must not expose the role field to non-admin callers — audit all User serialization paths.',
  ],

  confidence: 0.91,
};
