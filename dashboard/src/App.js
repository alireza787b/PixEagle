// src/App.js
import React from 'react';
import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';
import Dashboard from '/components/Dashboard';
import TrackerVisualization from '/components/TrackerVisualization';

const App = () => {
  return (
    <Router>
      <div>
        <Switch>
          <Route path="/dashboard" component={Dashboard} />
          <Route path="/visualization" component={TrackerVisualization} />
        </Switch>
      </div>
    </Router>
  );
};

export default App;
