SET SQL_SAFE_UPDATES = 0;

DROP DATABASE IF EXISTS database_schema;
CREATE DATABASE IF NOT EXISTS database_schema;
USE database_schema;

CREATE TABLE IF NOT EXISTS Users (
    user_id BIGINT PRIMARY KEY CHECK (user_id >= 100000),
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) DEFAULT ' ',
    role ENUM('admin', 'user') DEFAULT 'user',
    budget DECIMAL(15, 2) DEFAULT 5000 CHECK (budget >= 0), 
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Portfolios (
    portfolio_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    portfolio_name VARCHAR(100) NOT NULL DEFAULT 'My Portfolio',
    profit_loss DECIMAL(15, 2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Stocks (
    stock_id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(10) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    market VARCHAR(50) NOT NULL,
    quantity INT NOT NULL DEFAULT 0,
    current_price DECIMAL(10, 2) CHECK (current_price >= 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    portfolio_id INT NOT NULL,
    stock_id INT NOT NULL,
    transaction_type ENUM('buy', 'sell') NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    price_per_share DECIMAL(10, 2) NOT NULL CHECK (price_per_share >= 0),
    transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES Portfolios(portfolio_id) ON DELETE CASCADE,
    FOREIGN KEY (stock_id) REFERENCES Stocks(stock_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Watchlist (
    watchlist_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    stock_id INT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (stock_id) REFERENCES Stocks(stock_id) ON DELETE CASCADE,
    UNIQUE(user_id, stock_id)
);

CREATE TABLE IF NOT EXISTS Dividends (
    dividend_id INT AUTO_INCREMENT PRIMARY KEY,
    stock_id INT NOT NULL,
    dividend_amount DECIMAL(10, 2) CHECK (dividend_amount >= 0),
    payout_date DATE NOT NULL,
    FOREIGN KEY (stock_id) REFERENCES Stocks(stock_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS UserSettings (
    setting_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    setting_name VARCHAR(100) NOT NULL,
    setting_value VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
);

SET SESSION sql_mode = 'STRICT_ALL_TABLES';

DELIMITER $$

CREATE TRIGGER update_budget_after_transaction
AFTER INSERT ON Transactions
FOR EACH ROW
BEGIN
    DECLARE transaction_cost DECIMAL(15, 2);
    SET transaction_cost = NEW.quantity * NEW.price_per_share;

    IF NEW.transaction_type = 'buy' THEN
        UPDATE Users
        SET budget = budget - transaction_cost
        WHERE user_id = (SELECT user_id FROM Portfolios WHERE portfolio_id = NEW.portfolio_id);
    ELSEIF NEW.transaction_type = 'sell' THEN
        UPDATE Users
        SET budget = budget + transaction_cost
        WHERE user_id = (SELECT user_id FROM Portfolios WHERE portfolio_id = NEW.portfolio_id);
    END IF;
END $$

DELIMITER $$

CREATE TRIGGER prevent_excessive_buying
BEFORE INSERT ON Transactions
FOR EACH ROW
BEGIN
    DECLARE available_quantity INT;
    SELECT quantity INTO available_quantity
    FROM Stocks
    WHERE stock_id = NEW.stock_id;

    IF NEW.transaction_type = 'buy' THEN
        IF available_quantity < NEW.quantity THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Not enough stock available for the requested purchase.';
        END IF;
    END IF;
END $$

DELIMITER $$

CREATE TRIGGER update_stock_quantity_after_transaction
AFTER INSERT ON Transactions
FOR EACH ROW
BEGIN
    IF NEW.transaction_type = 'buy' THEN
        UPDATE Stocks
        SET quantity = quantity - NEW.quantity
        WHERE stock_id = NEW.stock_id;
    ELSEIF NEW.transaction_type = 'sell' THEN
        UPDATE Stocks
        SET quantity = quantity + NEW.quantity
        WHERE stock_id = NEW.stock_id;
    END IF;
END $$

DELIMITER $$

CREATE TRIGGER check_budget_before_transaction
BEFORE INSERT ON Transactions
FOR EACH ROW
BEGIN
    DECLARE user_budget DECIMAL(15, 2);
    DECLARE total_cost DECIMAL(15, 2);
    DECLARE portfolio_user_id INT;

    SELECT U.budget, P.user_id INTO user_budget, portfolio_user_id 
    FROM Users U 
    INNER JOIN Portfolios P ON U.user_id = P.user_id
    WHERE P.portfolio_id = NEW.portfolio_id;

    SET total_cost = NEW.quantity * NEW.price_per_share;

    IF NEW.transaction_type = 'buy' THEN
        IF user_budget < total_cost THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Transaction exceeds budget.';
        END IF;
    END IF;
END $$

DELIMITER $$

CREATE TRIGGER prevent_excessive_selling
BEFORE INSERT ON Transactions
FOR EACH ROW
BEGIN
    DECLARE owned_quantity INT DEFAULT 0;

    IF NEW.transaction_type = 'sell' THEN
        SELECT COALESCE(SUM(t.quantity), 0) INTO owned_quantity
        FROM Transactions t
        WHERE t.portfolio_id = NEW.portfolio_id 
          AND t.stock_id = NEW.stock_id 
          AND t.transaction_type = 'buy';

        IF owned_quantity < NEW.quantity THEN
            SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'User is attempting to sell more stocks than owned';
        END IF;
    END IF;
END $$

DELIMITER $$

CREATE TRIGGER trg_update_portfolio_profit_loss
AFTER INSERT ON Transactions
FOR EACH ROW
BEGIN
    DECLARE total_buy DECIMAL(15,2) DEFAULT 0;
    DECLARE total_sell DECIMAL(15,2) DEFAULT 0;
    DECLARE current_value DECIMAL(15,2) DEFAULT 0;
    DECLARE portfolio_profit_loss DECIMAL(15,2) DEFAULT 0;

    SELECT COALESCE(SUM(quantity * price_per_share), 0) INTO total_buy
    FROM Transactions
    WHERE portfolio_id = NEW.portfolio_id AND transaction_type = 'buy';

    SELECT COALESCE(SUM(quantity * price_per_share), 0) INTO total_sell
    FROM Transactions
    WHERE portfolio_id = NEW.portfolio_id AND transaction_type = 'sell';

    SELECT COALESCE(SUM(t.quantity * s.current_price), 0) INTO current_value
    FROM Transactions t
    JOIN Stocks s ON t.stock_id = s.stock_id
    WHERE t.portfolio_id = NEW.portfolio_id 
      AND t.transaction_type = 'buy'
      AND t.quantity > (
          SELECT COALESCE(SUM(quantity), 0)
          FROM Transactions
          WHERE portfolio_id = t.portfolio_id 
          AND stock_id = t.stock_id 
          AND transaction_type = 'sell'
      );

    SET portfolio_profit_loss = (total_sell + current_value) - total_buy;

    UPDATE Portfolios
    SET profit_loss = portfolio_profit_loss
    WHERE portfolio_id = NEW.portfolio_id;
END $$

DELIMITER ;

CREATE VIEW PortfolioView AS
SELECT 
    P.portfolio_id,
    U.user_id,
    U.username, 
    CONCAT(U.first_name, U.last_name) AS full_name,
    U.budget AS remaining_budget, 
    P.profit_loss,
    U.created_at AS member_since
FROM 
    Portfolios P
JOIN 
    Users U ON P.user_id = U.user_id;

CREATE VIEW SoldView AS
SELECT DISTINCTROW
    S.name,
    T.quantity,
    T.price_per_share AS price_purchased,
    S.current_price AS its_current_price,
    S.dividend_amount * T.quantity AS total_dividend,
    T.transaction_date AS date_sold,
    (S.dividend_amount + T.price_per_share) * T.quantity AS money_received,
    P.user_id
FROM 
    Transactions T
JOIN 
    (SELECT * FROM Stocks S1 NATURAL LEFT JOIN Dividends D) AS S ON T.stock_id = S.stock_id
JOIN 
    Portfolios P ON P.portfolio_id = T.portfolio_id
WHERE 
    P.user_id = 100005 
    AND T.transaction_type = 'sell'
ORDER BY 
    T.transaction_id;

CREATE VIEW HomeView AS
SELECT DISTINCTROW
    S.name,
    T.quantity,
    T.price_per_share AS price_purchased,
    S.current_price,
    S.dividend_amount * T.quantity AS total_dividend,
    (S.dividend_amount + S.current_price - T.price_per_share) * T.quantity AS profit_loss_possible,
    P.user_id
FROM 
    Transactions T
JOIN 
    (SELECT * FROM Stocks S1 NATURAL LEFT JOIN Dividends D) AS S ON T.stock_id = S.stock_id
JOIN 
    Portfolios P ON P.portfolio_id = T.portfolio_id
WHERE 
    P.user_id = 100005 
    AND T.transaction_type = 'buy'
ORDER BY 
    T.transaction_id;

CREATE VIEW TransactionView AS
SELECT DISTINCTROW
    T.transaction_id,
    S.name AS stock_name,
    T.transaction_type,
    T.quantity,
    T.price_per_share,
    T.transaction_date AS transaction_time,
    (T.quantity * T.price_per_share) AS total_price,
    P.user_id
FROM 
    Transactions T
JOIN 
    Portfolios P ON T.portfolio_id = P.portfolio_id
JOIN 
    Stocks S ON T.stock_id = S.stock_id
WHERE 
    P.user_id = 100005
ORDER BY 
    T.transaction_id;

CREATE VIEW StocksView AS 
SELECT 
    S.stock_id,
    S.name AS stock_name, 
    S.quantity AS number_available,
    S.current_price,
    S.market
FROM 
    Stocks S;

CREATE VIEW WatchlistView AS
SELECT 
    W.watchlist_id, 
    W.user_id,
    W.stock_id, 
    S.name,
    W.added_at
FROM 
    Watchlist W
JOIN 
    Stocks S ON W.stock_id = S.stock_id
WHERE 
    W.user_id = 100005
ORDER BY 
    W.added_at;


