import React, { useContext } from 'react';
import { IconButton } from '@mui/material';
import { Brightness4, Brightness7 } from '@mui/icons-material';
import { ThemeContext } from '../context/ThemeContext';

const ThemeToggle = () => {
  const { theme, toggleTheme } = useContext(ThemeContext);

  return (
    <IconButton onClick={toggleTheme} color="inherit">
      {theme === 'light' ? <Brightness4 /> : <Brightness7 />}
    </IconButton>
  );
};

export default ThemeToggle;
