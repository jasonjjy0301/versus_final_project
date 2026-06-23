-- VERSUS skeleton schema
-- Run:  mysql -u root -p versus < schema.sql
--
-- The four core tables for Phase I.
-- Students will extend with: predictions, votes, achievements,
-- user_achievements, follows, comments, plus triggers and a stored procedure.

DROP DATABASE IF EXISTS versus;
CREATE DATABASE versus;
USE versus;

CREATE TABLE Users (
    user_id       INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password      VARCHAR(255) NOT NULL,
    bio           TEXT,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE Brackets (
    bracket_id           INT AUTO_INCREMENT PRIMARY KEY,
    host_id              INT NOT NULL,
    title                VARCHAR(255) NOT NULL,
    description          TEXT,
    entrant_count        INT NOT NULL,
    status               ENUM(
                             'draft',
                             'predictions_open',
                             'round_1','round_2','round_3','round_4','round_5',
                             'completed'
                         ) NOT NULL DEFAULT 'predictions_open',
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_entrant_count CHECK (entrant_count IN (4,8,16,32)),
    CONSTRAINT fk_brackets_host  FOREIGN KEY (host_id) REFERENCES Users(user_id)
);

CREATE TABLE Entrants (
    entrant_id   INT AUTO_INCREMENT PRIMARY KEY,
    bracket_id   INT NOT NULL,
    seed         INT NOT NULL,
    name         VARCHAR(255) NOT NULL,
    CONSTRAINT fk_entrants_bracket FOREIGN KEY (bracket_id) REFERENCES Brackets(bracket_id),
    CONSTRAINT uq_entrants_seed    UNIQUE (bracket_id, seed)
);

CREATE TABLE Matchups (
    matchup_id          INT AUTO_INCREMENT PRIMARY KEY,
    bracket_id          INT NOT NULL,
    round               INT NOT NULL,
    slot                INT NOT NULL,
    entrant_a_id        INT,
    entrant_b_id        INT,
    winner_entrant_id   INT,
    votes_a             INT NOT NULL DEFAULT 0,
    votes_b             INT NOT NULL DEFAULT 0,
    CONSTRAINT fk_matchups_bracket FOREIGN KEY (bracket_id)        REFERENCES Brackets(bracket_id),
    CONSTRAINT fk_matchups_a       FOREIGN KEY (entrant_a_id)      REFERENCES Entrants(entrant_id),
    CONSTRAINT fk_matchups_b       FOREIGN KEY (entrant_b_id)      REFERENCES Entrants(entrant_id),
    CONSTRAINT fk_matchups_winner  FOREIGN KEY (winner_entrant_id) REFERENCES Entrants(entrant_id),
    CONSTRAINT uq_matchups_slot    UNIQUE (bracket_id, round, slot)
);

CREATE TABLE Predictions (
    prediction_id 		INT AUTO_INCREMENT PRIMARY KEY,
    user_id 			INT NOT NULL,
    matchup_id 			INT NOT NULL,
    entrant_id 			INT NOT NULL,
    correct 			BOOLEAN,
    points_earned 		INT NOT NULL DEFAULT 0,

    CONSTRAINT fk_predictions_user_id			FOREIGN KEY (user_id) 		  REFERENCES Users(user_id),
    CONSTRAINT fk_predictions_matchups_id 		FOREIGN KEY (matchup_id)	  REFERENCES Matchups(matchup_id),
    CONSTRAINT fk_predictions_entrant_id		FOREIGN KEY (entrant_id)	  REFERENCES Entrants(entrant_id),
    UNIQUE (user_id, matchup_id)
);


DELIMITER $$
CREATE TRIGGER check_prediction BEFORE INSERT ON Predictions
FOR EACH ROW
BEGIN
    IF NOT EXISTS (
        SELECT *
        FROM Matchups M
        JOIN Brackets B ON M.bracket_id = B.bracket_id
        WHERE M.matchup_id = NEW.matchup_id AND B.status = 'predictions_open'
    ) THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Prediction error';
    END IF;
END$$
DELIMITER ;

CREATE TABLE Votes (
    vote_id 			INT AUTO_INCREMENT PRIMARY KEY,
    user_id 			INT NOT NULL,
    matchup_id 			INT NOT NULL,
    entrant_id 			INT NOT NULL,
    CONSTRAINT fk_votes_user_id 		FOREIGN KEY (user_id) 			REFERENCES Users(user_id),
	CONSTRAINT fk_votes_matchup_id 	FOREIGN KEY (matchup_id) 		REFERENCES Matchups(matchup_id),
	CONSTRAINT fk_votes_entrant_id 	FOREIGN KEY (entrant_id) 		REFERENCES Entrants(entrant_id),
    UNIQUE (user_id, matchup_id)
);

DELIMITER $$

CREATE TRIGGER check_vote BEFORE INSERT ON Votes
FOR EACH ROW
BEGIN
    IF NOT EXISTS (
        SELECT *
        FROM Matchups M
        JOIN Brackets B ON M.bracket_id = B.bracket_id
        WHERE M.matchup_id = NEW.matchup_id AND B.status = CONCAT('round_', M.round)
    ) THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Voting error';
    END IF;
END$$
DELIMITER ;

CREATE TABLE Achievements(
	A_code 				VARCHAR (50) PRIMARY KEY,
    A_name 				VARCHAR (50),
    A_description 		VARCHAR(255)
);



CREATE TABLE User_Achievements(
	user_id				INT NOT NULL,
    A_code 				VARCHAR (50) NOT NULL,
    awarded_at			DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_user_id_A_code 			PRIMARY KEY(user_id, A_code),
    CONSTRAINT fk_User_Achievements_user_id FOREIGN KEY (user_id) 				REFERENCES Users(user_id),
    CONSTRAINT fk_User_Achievements_A_code 	FOREIGN KEY (A_code) 				REFERENCES Achievements(A_code)
);

DELIMITER $$

CREATE TRIGGER Bracket_maker AFTER INSERT ON Brackets
FOR EACH ROW
BEGIN
	IF(
		(SELECT COUNT(*) 
        FROM Brackets b 
        WHERE b.host_id = NEW.host_id
    ) = 1)
    THEN
		INSERT INTO User_Achievements
        SET user_id = NEW.host_id,
			A_code  = 'bracket_maker',
            awarded_at  = CURRENT_TIMESTAMP;
	END IF;
END$$
DELIMITER ;

DELIMITER $$
CREATE TRIGGER Locked_in AFTER INSERT ON Predictions
FOR EACH ROW
BEGIN
	IF(
		(SELECT COUNT(*) 
        FROM Predictions p
        WHERE p.user_id = NEW.user_id)=10)
	THEN
		INSERT INTO User_Achievements
        SET user_id = NEW.user_id,
			A_code  = 'locked_in',
            awarded_at  = CURRENT_TIMESTAMP;
	END IF;
END$$
DELIMITER ;

INSERT INTO Achievements VALUES 
('bracket_maker', 'bracket maker','Host first bracket'),
('locked_in', 'locked in','submit 10th prediction ');

CREATE INDEX idx_brackets_host
ON Brackets(host_id);

CREATE INDEX idx_comments_matchup
ON Comments(matchup_id);

CREATE INDEX idx_predictions_user
ON Predictions(user_id);

CREATE INDEX idx_votes_matchup
ON Votes(matchup_id);

CREATE INDEX idx_follow_followed
ON Follow(followed_id);

CREATE TABLE Follow(
	follower_id			INT NOT NULL,
    followed_id			INT NOT NULL,
    created_at			DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_follower_id_followed_id	PRIMARY KEY(follower_id, followed_id),
    CONSTRAINT fk_follower_id 				FOREIGN KEY (follower_id) 				REFERENCES Users(user_id),
    CONSTRAINT followed_id 					FOREIGN KEY (followed_id) 				REFERENCES Users(user_id),
    CHECK (follower_id <> followed_id)
);
CREATE TABLE Comments (
	comment_id 	        INT AUTO_INCREMENT PRIMARY KEY,
    user_id				INT NOT NULL,
    matchup_id			INT NOT NULL,
    body				VARCHAR(255),
    created_at    		DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_comments_matchup_id       FOREIGN KEY (matchup_id)        	REFERENCES Matchups(matchup_id),  
    CONSTRAINT fk_comments_user_id		   	FOREIGN KEY (user_id)		   		REFERENCES Users(user_id)
);




