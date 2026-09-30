import { sql } from 'drizzle-orm';
import { sqliteTable, integer, text, primaryKey, check } from 'drizzle-orm/sqlite-core';
import { user } from './auth.schema';

export * from './auth.schema';

export const post = sqliteTable('post', {
	id: integer().primaryKey({ autoIncrement: true }),
	content: text().notNull(),
	authorId: text('author_id').references(() => user.id, { onDelete: 'set null' }),
	authorName: text('author_name').notNull(),
	createdAt: integer('created_at', { mode: 'timestamp_ms' })
		.default(sql`(cast(unixepoch('subsecond') * 1000 as integer))`)
		.notNull(),
	lang: text().default('en'),
	translations: text({ mode: 'json' }).default('{}'),
	upvotes: integer().notNull().default(0),
	downvotes: integer().notNull().default(0)
});

export const vote = sqliteTable(
	'vote',
	{
		voterId: text('voter_id')
			.references(() => user.id, { onDelete: 'cascade' })
			.notNull(),
		postId: integer('post_id')
			.references(() => post.id, { onDelete: 'cascade' })
			.notNull(),
		value: integer().notNull()
	},
	(table) => [
		primaryKey({ columns: [table.voterId, table.postId] }),
		check('vote_value_check', sql`${table.value} IN (-1, 1)`)
	]
);

export const report = sqliteTable(
	'report',
	{
		reporterId: text('reporter_id')
			.references(() => user.id, { onDelete: 'cascade' })
			.notNull(),
		postId: integer('post_id')
			.references(() => post.id, { onDelete: 'cascade' })
			.notNull(),
		reason: text({
			enum: ['harassement', 'mild_language', 'link', 'offensive_name']
		}).notNull(),
		quote: text()
	},
	(table) => [primaryKey({ columns: [table.reporterId, table.postId] })]
);

export const ban = sqliteTable('ban', {
	emailHash: text('email_hash').primaryKey(),
	userId: text('user_id').references(() => user.id, { onDelete: 'set null' }),
	bannedPostContent: text('banned_post_content').notNull(),
	reason: text({
		enum: ['harassement', 'mild_language', 'link', 'offensive_name']
	}).notNull(),
	quote: text(),
	active: integer({ mode: 'boolean' }).default(true).notNull(),
	createdAt: integer('created_at', { mode: 'timestamp_ms' })
		.default(sql`(cast(unixepoch('subsecond') * 1000 as integer))`)
		.notNull()
});

export const banAppeal = sqliteTable('ban_appeal', {
	id: integer().primaryKey({ autoIncrement: true }),
	banEmailHash: text('ban_email_hash')
		.references(() => ban.emailHash, { onDelete: 'cascade' })
		.notNull(),
	justification: text().notNull(),
	status: text({
		enum: ['pending', 'approved', 'rejected']
	})
		.default('pending')
		.notNull(),
	reviewedAt: integer('reviewed_at', { mode: 'timestamp_ms' }),
	decisionMessage: text('decision_message'),
	createdAt: integer('created_at', { mode: 'timestamp_ms' })
		.default(sql`(cast(unixepoch('subsecond') * 1000 as integer))`)
		.notNull()
});
