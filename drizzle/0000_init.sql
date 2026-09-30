CREATE TABLE `ban` (
	`email_hash` text PRIMARY KEY NOT NULL,
	`user_id` text,
	`banned_post_content` text NOT NULL,
	`reason` text NOT NULL,
	`quote` text,
	`active` integer DEFAULT true NOT NULL,
	`created_at` integer DEFAULT (cast(unixepoch('subsecond') * 1000 as integer)) NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE TABLE `ban_appeal` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`ban_email_hash` text NOT NULL,
	`justification` text NOT NULL,
	`status` text DEFAULT 'pending' NOT NULL,
	`reviewed_at` integer,
	`decision_message` text,
	`created_at` integer DEFAULT (cast(unixepoch('subsecond') * 1000 as integer)) NOT NULL,
	FOREIGN KEY (`ban_email_hash`) REFERENCES `ban`(`email_hash`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `post` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`content` text NOT NULL,
	`author_id` text,
	`author_name` text NOT NULL,
	`created_at` integer DEFAULT (cast(unixepoch('subsecond') * 1000 as integer)) NOT NULL,
	`lang` text DEFAULT 'en',
	`translations` text DEFAULT '{}',
	`upvotes` integer DEFAULT 0 NOT NULL,
	`downvotes` integer DEFAULT 0 NOT NULL,
	FOREIGN KEY (`author_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE TABLE `report` (
	`reporter_id` text NOT NULL,
	`post_id` integer NOT NULL,
	`reason` text NOT NULL,
	`quote` text,
	PRIMARY KEY(`reporter_id`, `post_id`),
	FOREIGN KEY (`reporter_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`post_id`) REFERENCES `post`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `vote` (
	`voter_id` text NOT NULL,
	`post_id` integer NOT NULL,
	`value` integer NOT NULL,
	PRIMARY KEY(`voter_id`, `post_id`),
	FOREIGN KEY (`voter_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`post_id`) REFERENCES `post`(`id`) ON UPDATE no action ON DELETE cascade,
	CONSTRAINT "vote_value_check" CHECK("vote"."value" IN (-1, 1))
);
--> statement-breakpoint
CREATE TABLE `account` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`account_id` text NOT NULL,
	`provider_id` text NOT NULL,
	`user_id` integer NOT NULL,
	`access_token` text,
	`refresh_token` text,
	`id_token` text,
	`access_token_expires_at` integer,
	`refresh_token_expires_at` integer,
	`scope` text,
	`password` text,
	`created_at` integer DEFAULT (cast(unixepoch('subsecond') * 1000 as integer)) NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `account_userId_idx` ON `account` (`user_id`);--> statement-breakpoint
CREATE TABLE `session` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`expires_at` integer NOT NULL,
	`token` text NOT NULL,
	`created_at` integer DEFAULT (cast(unixepoch('subsecond') * 1000 as integer)) NOT NULL,
	`updated_at` integer NOT NULL,
	`ip_address` text,
	`user_agent` text,
	`user_id` integer NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `user`(`id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `session_token_unique` ON `session` (`token`);--> statement-breakpoint
CREATE INDEX `session_userId_idx` ON `session` (`user_id`);--> statement-breakpoint
CREATE TABLE `user` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`name` text NOT NULL,
	`email` text NOT NULL,
	`email_verified` integer DEFAULT false NOT NULL,
	`image` text,
	`created_at` integer DEFAULT (cast(unixepoch('subsecond') * 1000 as integer)) NOT NULL,
	`updated_at` integer DEFAULT (cast(unixepoch('subsecond') * 1000 as integer)) NOT NULL,
	`role` text DEFAULT 'user',
	`lang` text DEFAULT 'en'
);
--> statement-breakpoint
CREATE UNIQUE INDEX `user_email_unique` ON `user` (`email`);--> statement-breakpoint
CREATE TABLE `verification` (
	`id` integer PRIMARY KEY AUTOINCREMENT NOT NULL,
	`identifier` text NOT NULL,
	`value` text NOT NULL,
	`expires_at` integer NOT NULL,
	`created_at` integer DEFAULT (cast(unixepoch('subsecond') * 1000 as integer)) NOT NULL,
	`updated_at` integer DEFAULT (cast(unixepoch('subsecond') * 1000 as integer)) NOT NULL
);
--> statement-breakpoint
CREATE INDEX `verification_identifier_idx` ON `verification` (`identifier`);