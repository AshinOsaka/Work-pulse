// Runs once, when the MongoDB data volume is first initialised.
// Creates a least-privilege application user scoped to the WorkPulse database,
// so the API never connects with root credentials.
const dbName = process.env.MONGO_APP_DB || 'workpulse'
const username = process.env.MONGO_APP_USERNAME
const password = process.env.MONGO_APP_PASSWORD

if (!username || !password) {
  throw new Error('MONGO_APP_USERNAME and MONGO_APP_PASSWORD must be set')
}

db.getSiblingDB(dbName).createUser({
  user: username,
  pwd: password,
  roles: [{ role: 'readWrite', db: dbName }],
})

print(`Created application user '${username}' on database '${dbName}'`)
