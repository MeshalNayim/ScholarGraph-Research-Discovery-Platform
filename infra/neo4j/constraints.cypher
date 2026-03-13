CREATE CONSTRAINT paper_paperId IF NOT EXISTS
FOR (p:Paper) REQUIRE p.paperId IS UNIQUE;

CREATE CONSTRAINT author_authorName IF NOT EXISTS
FOR (a:Author) REQUIRE a.authorName IS UNIQUE;

CREATE CONSTRAINT venue_venueName IF NOT EXISTS
FOR (v:Venue) REQUIRE v.venueName IS UNIQUE;

CREATE INDEX paper_year IF NOT EXISTS
FOR (p:Paper) ON (p.year);

