// Executed by Playwright CLI's run-code command against the live test server.
async (page) => {
  const errors = [];
  const callbacks = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('request', request => {
    if (request.url().includes('_dash-update-component')) callbacks.push(request.postDataJSON()?.output);
  });
  // Exercise recovery from browser state belonging to a previous server process.
  await page.evaluate(() => {
    sessionStorage.setItem('project-id', JSON.stringify('stale-browser-workspace'));
    sessionStorage.setItem('project-id-timestamp', String(Date.now()));
  });
  await page.reload();
  await page.waitForFunction(() => {
    const id = JSON.parse(sessionStorage.getItem('project-id'));
    return id && id !== 'stale-browser-workspace';
  }, null, {timeout: 10000});

  const routes = [
    ['/project', 'Project Workspace'], ['/export', 'Report Center'],
    ['/compare', 'Compare Workspace'], ['/dsc', 'DSC Analysis'],
    ['/tga', 'TGA Analysis'], ['/dta', 'DTA Analysis'],
    ['/ftir', 'FTIR Analysis'], ['/raman', 'RAMAN Analysis'],
    ['/xrd', 'XRD Analysis'], ['/about', 'About MaterialScope'], ['/', 'Data Import'],
  ];
  const timings = [];
  for (const [route, heading] of routes) {
    const start = Date.now();
    await page.locator('.sidebar a[href="' + route + '"]').click();
    await page.getByRole('heading', {name: heading, exact: true}).waitFor({state: 'visible', timeout: 10000});
    timings.push({route, ms: Date.now() - start});
  }

  const samples = [
    ['DSC', 'dsc_polymer_melting.csv'], ['TGA', 'tga_calcium_oxalate.csv'],
    ['DTA', 'dta_tnaa_5c_mendeley.csv'], ['FTIR', 'ftir_particleboard_50g_figshare.csv'],
    ['RAMAN', 'raman_cnt_figshare.csv'], ['XRD', 'xrd_2024_0304_zenodo.csv'],
  ];
  const imported = [];
  for (const [modality, filename] of samples) {
    await page.locator('#wizard-step-1').getByRole('button', {name: new RegExp('^' + modality + ' ')}).click();
    await page.locator('#file-upload input[type=file]').setInputFiles('sample_data/' + filename);
    await page.locator('#mapping-preview-status').getByText(/Preview ready:/).waitFor({state: 'attached'});
    await page.getByRole('button', {name: 'Next: Preview', exact: true}).click();
    await page.getByRole('button', {name: 'Next: Map Columns', exact: true}).click();
    await page.getByRole('button', {name: 'Next: Review', exact: true}).click();
    await page.getByRole('button', {name: 'Next: Confirm Import', exact: true}).click();
    await page.getByRole('button', {name: 'Confirm Import', exact: true}).click();
    await page.locator('#wizard-step-1').waitFor({state: 'visible', timeout: 10000});
    await page.locator('#modality-select-status').getByText(/Imported/).waitFor({state: 'visible'});
    const datasets = await page.evaluate(async () => {
      const project = JSON.parse(sessionStorage.getItem('project-id'));
      return (await (await fetch('/workspace/' + project + '/datasets')).json()).datasets;
    });
    if (datasets.length !== imported.length + 1 || !datasets.some(d => d.data_type === modality && d.key === filename)) {
      throw new Error('Confirm Import did not create ' + modality + ': ' + JSON.stringify(datasets));
    }
    imported.push(modality);
  }
  // Revisit Report Center with real data to check its dynamically mounted controls.
  await page.locator('.sidebar a[href="/export"]').click();
  await page.locator('#prepare-support-snapshot-btn').waitFor({state: 'visible'});
  await page.waitForFunction(() => document.title !== 'MaterialScope ...');
  await page.waitForTimeout(1500);
  const settled = callbacks.length;
  await page.waitForTimeout(3000);
  if (callbacks.length !== settled) throw new Error('Callbacks did not settle: ' + JSON.stringify(callbacks.slice(settled)));
  if (errors.length) throw new Error(JSON.stringify(errors));
  return {routes: timings, imported, idleCallbacks: 0, browserErrors: errors};
}
