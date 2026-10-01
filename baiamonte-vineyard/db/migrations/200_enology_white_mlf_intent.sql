ALTER TABLE enology_recipe_preferences
  ADD COLUMN mlf_intent ENUM('undecided','allow','block') NOT NULL DEFAULT 'undecided' AFTER style_target;
