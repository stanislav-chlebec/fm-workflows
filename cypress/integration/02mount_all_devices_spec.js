describe('Mount all devices from inventory', function() {
  beforeEach(function() {
    cy.login()

    cy.unmount_all_devices()
  })

  //prerequisite: all devices unmounted
  it('mounts all devices from inventory', function() {
    cy.server({
      method: 'POST',
    })
    cy.route('/api/conductor/workflow').as('getWorkflowId')

    cy.server({
      method: 'GET',
    })
    cy.route('/api/conductor/executions/').as('getWorkflow') //uanble to match following string
//Cypress.minimatch('http://10.103.5.231/api/conductor/executions/?q=&h=&freeText=(workflowId:a1e22fcc-dfd6-4edd-8d80-c9bb0c7d9a86+workflowType:/.*[Aa][11][Ee][22][22][Ff][Cc][Cc][--][Dd][Ff][Dd][66][--][44][Ee][Dd][Dd][--][88][Dd][88][00][--][Cc][99][Bb][Bb][00][Cc][77][Dd][99][Aa][88][66].*/)&start=0&size=20', '/api/conductor/executions/**', {
//  matchBase: true
//})

    cy.server({
      method: 'GET',
    })
    cy.route('/api/odl/oper/all/status/cli').as('getAllStatusCli')
    cy.route('/api/odl/oper/all/status/topology-netconf').as('getAllStatusNetconf')


    cy.visit('/')

    cy.contains('UniConfig').click()
    cy.get('table tbody tr').should('not.to.exist')

    cy.get('.navbar-brand').click()
    cy.contains('Workflows').click()

    cy.url().should('include', '/workflows/defs')
    cy.get('input[placeholder="Search by keyword."').type('Mount_all_from_inventory')
    //cy.contains('Mount_all_from_inventory').click()
    //cy.get('button[title="Execute"]').click()
    cy.get('button[title="Execute"]').click()

    cy.get('div.modal-content').contains('Execute').click()
    cy.wait('@getWorkflowId')
    cy.get('div.modal-content').contains('Execute').should('not.to.exist')
    cy.get('div.modal-content').contains('OK')
    //this explicit wait is needed to wait for completing of procesing on chain ConductorServer<->ElasticSearch<->Dyn
    cy.wait(3000)
    //hopufully now we are ready to go - let us click the workflow id link
    cy.get('div.modal-footer a:first-child').click()
    //cy.wait('@getWorkflow') //timeout because unable to match route string

    cy.url().should('include', '/workflows/exec')
    //here should be a wait but I did not succeed with waiting for xhr
    cy.get('div.modal-header').contains('Details of Mount_all_from_inventory',{timeout:30000})
    cy.contains('Close').scrollIntoView()
    //cy.get('div.headerInfo').contains('COMPLETED',{timeout:90000})

    //20200610 add this wait before clicking because it seems that sometimes when button is clicked nothing is going to happen
    //so next assert waiting for appearing of dialog with title "Details of Dynamic_fork" would fail
    cy.wait(4000)
    cy.get('#row-1',{timeout:30000})
    cy.contains('SUB_WORKFLOW').next().find('button').click()
    //cy.contains('create_loopback').click({force:true}) //this did not work
    //cy.contains('Children').click().get('a') // neither worked

    //cy.wait(5000)
    cy.contains('Details of Dynamic_fork',{timeout:300000})
    cy.contains('Close').scrollIntoView()
    cy.get('div.headerInfo').contains('COMPLETED',{timeout:300000})
    cy.get('div.heightWrapper').scrollTo('bottom', { duration: 1000 })

    cy.contains('Input/Output').click()
    cy.contains('JSON').click()
    cy.contains('Edit & Rerun').click()
    cy.contains('Execution Flow').click()
    cy.get('#detailTabs-tabpane-execFlow > div').scrollTo('bottomRight', { duration: 1000 })
    cy.contains('Task Details').click()

    cy.contains('Parent').click()

    //cy.contains('Children').click()
    //does not work in v1.1.0

    cy.contains('Input/Output').click()
    cy.contains('JSON').click()
    cy.contains('Edit & Rerun').click()
    cy.contains('Execution Flow').click()
    cy.contains('Task Details').click()

    cy.contains('Close').click()
    cy.get('span.navbar-brand img').click()
    cy.contains('UniConfig').click()

    cy.get('table tbody tr:nth-child(8)').should('to.exist')
  })
})
