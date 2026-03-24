---
title: Administration
description: User management, registration modes, and system administration
category: Configuration
order: 10
keywords: [admin, users, registration, invite, administrator, management]
---

# Administration

The Administration panel is available to users with the **administrator** role. It provides user management and system configuration options.

## Accessing Admin Features

Admin features are accessed via the **Users** tab, which only appears for administrator accounts.

## User Management

### Viewing Users
The admin panel displays all registered users with:
- Username and display name
- Account type (user or administrator)
- Account creation date

### Creating Users
Administrators can create new user accounts directly:
1. Click **Add User**
2. Enter username, display name, and password
3. Select the account type
4. The new user can log in immediately

### Editing Users
- Change a user's display name
- Promote a user to administrator (or demote)
- Reset a user's password

### Deleting Users
Remove user accounts that are no longer needed. This action is permanent.

## Registration Modes

Control how new users can join the system:

| Mode | Description |
|------|-------------|
| **Disabled** | No self-registration; admin must create all accounts |
| **Invite Only** | Users can register only with a valid invitation code |
| **Open** | Anyone can create an account |

### Invitation Codes
When registration mode is set to **Invite Only**:

1. Generate invitation codes from the admin panel
2. Share codes with people you want to invite
3. Users enter the code during registration
4. Codes can be single-use or multi-use

## Data Isolation

TomeVox enforces data isolation between users:

- **Projects** — Each user can only see their own projects
- **Custom Voices** — Voice uploads are private to each user
- **Jobs** — Users only see jobs for their own projects
- **TTS Engines** — Engines can be private (owner only) or shared (visible to all)

### Shared Engines
Administrators can mark TTS engines as **shared**, making them available to all users. This is useful for shared infrastructure or organization-wide engines.

### Administrator Access
Administrators can see all users' data for troubleshooting and management purposes.

## Security Recommendations

1. **Change the default password** — The initial `Administrator` / `ChangeMe` credentials should be changed immediately
2. **Use strong passwords** — Encourage all users to use strong, unique passwords
3. **Limit admin accounts** — Only grant administrator access when necessary
4. **Review registration mode** — Keep registration disabled or invite-only for private deployments

## Next Steps

- [Getting Started](./getting-started) — Share this guide with new users
- [Settings](./settings) — Configure system-wide defaults
