import { Express, Request, Response, NextFunction } from "express";
import session from "express-session";
import passport from "passport";
import { Strategy as LocalStrategy } from "passport-local";
import bcrypt from "bcryptjs";
import crypto from "crypto";
import pg from "pg";
import connectPgSimple from "connect-pg-simple";
import {
  loginSchema,
  registerSchema,
  changePasswordSchema,
  insertUserSchema,
} from "@shared/schema";

const PgSession = connectPgSimple(session);

interface DbUser {
  id: string;
  username: string;
  email: string | null;
  password_hash: string;
  display_name: string | null;
  user_type: string;
  is_enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

function toPublicUser(u: DbUser) {
  return {
    id: u.id,
    username: u.username,
    email: u.email,
    displayName: u.display_name,
    userType: u.user_type,
    isEnabled: u.is_enabled,
    createdAt: u.created_at,
    updatedAt: u.updated_at,
  };
}

let pool: pg.Pool;

function getPool() {
  if (!pool) {
    pool = new pg.Pool({ connectionString: process.env.DATABASE_URL });
  }
  return pool;
}

async function findUserByUsername(username: string): Promise<DbUser | null> {
  const { rows } = await getPool().query(
    "SELECT * FROM users WHERE username = $1",
    [username]
  );
  return rows[0] || null;
}

async function findUserById(id: string): Promise<DbUser | null> {
  const { rows } = await getPool().query(
    "SELECT * FROM users WHERE id = $1",
    [id]
  );
  return rows[0] || null;
}

async function getRegistrationMode(): Promise<string> {
  const { rows } = await getPool().query(
    "SELECT value FROM system_settings WHERE key = 'registration_mode'"
  );
  return rows[0]?.value || "disabled";
}

export function ensureAuthenticated(
  req: Request,
  res: Response,
  next: NextFunction
) {
  if (req.isAuthenticated()) return next();
  res.status(401).json({ error: "Authentication required" });
}

export function ensureAdmin(
  req: Request,
  res: Response,
  next: NextFunction
) {
  if (!req.isAuthenticated()) {
    return res.status(401).json({ error: "Authentication required" });
  }
  const user = req.user as DbUser;
  if (user.user_type !== "administrator") {
    return res.status(403).json({ error: "Administrator access required" });
  }
  next();
}

export async function setupAuth(app: Express) {
  const pgPool = getPool();

  app.use(
    session({
      store: new PgSession({
        pool: pgPool,
        createTableIfMissing: true,
      }),
      secret: process.env.SESSION_SECRET || "voxlibris-secret-key-change-in-production",
      resave: false,
      saveUninitialized: false,
      cookie: {
        maxAge: 30 * 24 * 60 * 60 * 1000,
        httpOnly: true,
        secure: false,
        sameSite: "lax",
      },
    })
  );

  app.use(passport.initialize());
  app.use(passport.session());

  passport.use(
    new LocalStrategy(async (username, password, done) => {
      try {
        const user = await findUserByUsername(username);
        if (!user) return done(null, false, { message: "Invalid credentials" });
        if (!user.is_enabled)
          return done(null, false, { message: "Account is disabled" });
        const match = await bcrypt.compare(password, user.password_hash);
        if (!match) return done(null, false, { message: "Invalid credentials" });
        return done(null, user);
      } catch (err) {
        return done(err);
      }
    })
  );

  passport.serializeUser((user: any, done) => {
    done(null, user.id);
  });

  passport.deserializeUser(async (id: string, done) => {
    try {
      const user = await findUserById(id);
      if (user && !user.is_enabled) {
        return done(null, false);
      }
      done(null, user);
    } catch (err) {
      done(err);
    }
  });

  app.get("/api/auth/registration-mode", async (_req, res) => {
    try {
      const mode = await getRegistrationMode();
      res.json({ mode });
    } catch {
      res.json({ mode: "disabled" });
    }
  });

  app.post("/api/auth/login", (req: Request, res: Response, next: NextFunction) => {
    const parsed = loginSchema.safeParse(req.body);
    if (!parsed.success) {
      return res.status(400).json({ error: "Invalid request", details: parsed.error.errors });
    }

    passport.authenticate("local", (err: any, user: DbUser | false, info: any) => {
      if (err) return next(err);
      if (!user) return res.status(401).json({ error: info?.message || "Invalid credentials" });
      req.logIn(user, (loginErr) => {
        if (loginErr) return next(loginErr);
        return res.json({ user: toPublicUser(user) });
      });
    })(req, res, next);
  });

  app.post("/api/auth/logout", (req, res) => {
    req.logout((err) => {
      if (err) return res.status(500).json({ error: "Logout failed" });
      req.session.destroy(() => {
        res.clearCookie("connect.sid");
        res.json({ success: true });
      });
    });
  });

  app.get("/api/auth/me", (req, res) => {
    if (!req.isAuthenticated()) {
      return res.status(401).json({ error: "Not authenticated" });
    }
    res.json({ user: toPublicUser(req.user as DbUser) });
  });

  app.post("/api/auth/register", async (req: Request, res: Response) => {
    try {
      const parsed = registerSchema.safeParse(req.body);
      if (!parsed.success) {
        return res.status(400).json({ error: "Invalid request", details: parsed.error.errors });
      }
      const { username, password, email, ageConfirmed, invitationCode } = parsed.data;

      const mode = await getRegistrationMode();
      if (mode === "disabled") {
        return res.status(403).json({ error: "Registration is currently disabled" });
      }

      if (mode === "invite-only") {
        if (!invitationCode) {
          return res.status(400).json({ error: "Invitation code is required" });
        }
        const { rows } = await pgPool.query(
          "SELECT * FROM invitation_codes WHERE code = $1 AND used_by IS NULL",
          [invitationCode]
        );
        if (rows.length === 0) {
          return res.status(400).json({ error: "Invalid or already used invitation code" });
        }
      }

      const existing = await findUserByUsername(username);
      if (existing) {
        return res.status(409).json({ error: "Username already taken" });
      }

      const hashedPassword = await bcrypt.hash(password, 10);
      const userId = crypto.randomUUID();

      const client = await pgPool.connect();
      try {
        await client.query("BEGIN");

        await client.query(
          `INSERT INTO users (id, username, email, password_hash, display_name, user_type, is_enabled, created_at, updated_at)
           VALUES ($1, $2, $3, $4, $5, 'user', true, NOW(), NOW())`,
          [userId, username, email, hashedPassword, username]
        );

        if (mode === "invite-only" && invitationCode) {
          const { rowCount } = await client.query(
            "UPDATE invitation_codes SET used_by = $1, used_at = NOW() WHERE code = $2 AND used_by IS NULL",
            [userId, invitationCode]
          );
          if (rowCount === 0) {
            await client.query("ROLLBACK");
            return res.status(400).json({ error: "Invitation code already used" });
          }
        }

        await client.query("COMMIT");
      } catch (txErr) {
        await client.query("ROLLBACK");
        throw txErr;
      } finally {
        client.release();
      }

      const newUser = await findUserById(userId);
      if (!newUser) {
        return res.status(500).json({ error: "User creation failed" });
      }

      req.logIn(newUser, (err) => {
        if (err) return res.status(500).json({ error: "Login after registration failed" });
        return res.json({ user: toPublicUser(newUser) });
      });
    } catch (err: any) {
      console.error("Registration error:", err);
      res.status(500).json({ error: "Registration failed" });
    }
  });

  app.post("/api/auth/change-password", ensureAuthenticated, async (req: Request, res: Response) => {
    try {
      const parsed = changePasswordSchema.safeParse(req.body);
      if (!parsed.success) {
        return res.status(400).json({ error: "Invalid request", details: parsed.error.errors });
      }
      const { currentPassword, newPassword } = parsed.data;
      const user = req.user as DbUser;

      const match = await bcrypt.compare(currentPassword, user.password_hash);
      if (!match) {
        return res.status(400).json({ error: "Current password is incorrect" });
      }

      const hashedPassword = await bcrypt.hash(newPassword, 10);
      await pgPool.query(
        "UPDATE users SET password_hash = $1, updated_at = NOW() WHERE id = $2",
        [hashedPassword, user.id]
      );

      res.json({ success: true });
    } catch (err) {
      console.error("Change password error:", err);
      res.status(500).json({ error: "Failed to change password" });
    }
  });

  app.get("/api/admin/users", ensureAdmin, async (_req, res) => {
    try {
      const { rows } = await pgPool.query(
        "SELECT * FROM users ORDER BY created_at ASC"
      );
      res.json(rows.map(toPublicUser));
    } catch (err) {
      res.status(500).json({ error: "Failed to fetch users" });
    }
  });

  app.post("/api/admin/users", ensureAdmin, async (req: Request, res: Response) => {
    try {
      const parsed = insertUserSchema.safeParse(req.body);
      if (!parsed.success) {
        return res.status(400).json({ error: "Invalid request", details: parsed.error.errors });
      }
      const { username, password, email, displayName, userType } = parsed.data;

      const existing = await findUserByUsername(username);
      if (existing) {
        return res.status(409).json({ error: "Username already taken" });
      }

      const hashedPassword = await bcrypt.hash(password, 10);
      const userId = crypto.randomUUID();

      await pgPool.query(
        `INSERT INTO users (id, username, email, password_hash, display_name, user_type, is_enabled, created_at, updated_at)
         VALUES ($1, $2, $3, $4, $5, $6, true, NOW(), NOW())`,
        [userId, username, email || null, hashedPassword, displayName || username, userType || "user"]
      );

      const newUser = await findUserById(userId);
      res.json(toPublicUser(newUser!));
    } catch (err) {
      console.error("Create user error:", err);
      res.status(500).json({ error: "Failed to create user" });
    }
  });

  app.patch("/api/admin/users/:id", ensureAdmin, async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const { isEnabled, userType, displayName, email } = req.body;
      const updates: string[] = [];
      const values: any[] = [];
      let idx = 1;

      if (typeof isEnabled === "boolean") {
        updates.push(`is_enabled = $${idx++}`);
        values.push(isEnabled);
      }
      if (userType) {
        updates.push(`user_type = $${idx++}`);
        values.push(userType);
      }
      if (typeof displayName === "string") {
        updates.push(`display_name = $${idx++}`);
        values.push(displayName);
      }
      if (typeof email === "string") {
        updates.push(`email = $${idx++}`);
        values.push(email);
      }

      if (updates.length === 0) {
        return res.status(400).json({ error: "No fields to update" });
      }

      updates.push(`updated_at = NOW()`);
      values.push(id);

      await pgPool.query(
        `UPDATE users SET ${updates.join(", ")} WHERE id = $${idx}`,
        values
      );

      const updated = await findUserById(id);
      if (!updated) return res.status(404).json({ error: "User not found" });
      res.json(toPublicUser(updated));
    } catch (err) {
      console.error("Update user error:", err);
      res.status(500).json({ error: "Failed to update user" });
    }
  });

  app.delete("/api/admin/users/:id", ensureAdmin, async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const currentUser = req.user as DbUser;
      if (currentUser.id === id) {
        return res.status(400).json({ error: "Cannot delete your own account" });
      }
      await pgPool.query("DELETE FROM users WHERE id = $1", [id]);
      res.json({ success: true });
    } catch (err) {
      res.status(500).json({ error: "Failed to delete user" });
    }
  });

  app.post("/api/admin/users/:id/reset-password", ensureAdmin, async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const { newPassword } = req.body;
      if (!newPassword || newPassword.length < 4) {
        return res.status(400).json({ error: "Password must be at least 4 characters" });
      }
      const hashedPassword = await bcrypt.hash(newPassword, 10);
      await pgPool.query(
        "UPDATE users SET password_hash = $1, updated_at = NOW() WHERE id = $2",
        [hashedPassword, id]
      );
      res.json({ success: true });
    } catch (err) {
      res.status(500).json({ error: "Failed to reset password" });
    }
  });

  app.get("/api/admin/settings/registration-mode", ensureAdmin, async (_req, res) => {
    try {
      const mode = await getRegistrationMode();
      res.json({ mode });
    } catch {
      res.json({ mode: "disabled" });
    }
  });

  app.put("/api/admin/settings/registration-mode", ensureAdmin, async (req: Request, res: Response) => {
    try {
      const { mode } = req.body;
      if (!["disabled", "invite-only", "open"].includes(mode)) {
        return res.status(400).json({ error: "Invalid mode" });
      }
      await pgPool.query(
        `INSERT INTO system_settings (key, value, updated_at) VALUES ('registration_mode', $1, NOW())
         ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()`,
        [mode]
      );
      res.json({ mode });
    } catch (err) {
      res.status(500).json({ error: "Failed to update registration mode" });
    }
  });

  app.get("/api/admin/invitation-codes", ensureAdmin, async (_req, res) => {
    try {
      const { rows } = await pgPool.query(
        `SELECT ic.*, 
                creator.username as creator_username,
                consumer.username as consumer_username
         FROM invitation_codes ic
         LEFT JOIN users creator ON ic.created_by = creator.id
         LEFT JOIN users consumer ON ic.used_by = consumer.id
         ORDER BY ic.created_at DESC`
      );
      res.json(
        rows.map((r) => ({
          id: r.id,
          code: r.code,
          createdBy: r.creator_username || r.created_by,
          usedBy: r.consumer_username || r.used_by,
          createdAt: r.created_at,
          usedAt: r.used_at,
        }))
      );
    } catch (err) {
      res.status(500).json({ error: "Failed to fetch invitation codes" });
    }
  });

  app.post("/api/admin/invitation-codes", ensureAdmin, async (req: Request, res: Response) => {
    try {
      const admin = req.user as DbUser;
      const code = crypto.randomBytes(6).toString("hex").toUpperCase();
      const id = crypto.randomUUID();
      await pgPool.query(
        "INSERT INTO invitation_codes (id, code, created_by, created_at) VALUES ($1, $2, $3, NOW())",
        [id, code, admin.id]
      );
      res.json({ id, code, createdBy: admin.username, usedBy: null, createdAt: new Date().toISOString(), usedAt: null });
    } catch (err) {
      res.status(500).json({ error: "Failed to generate invitation code" });
    }
  });

  app.delete("/api/admin/invitation-codes/:id", ensureAdmin, async (req: Request, res: Response) => {
    try {
      await pgPool.query("DELETE FROM invitation_codes WHERE id = $1", [req.params.id]);
      res.json({ success: true });
    } catch (err) {
      res.status(500).json({ error: "Failed to delete invitation code" });
    }
  });
}
