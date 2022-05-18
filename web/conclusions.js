
function SetupConclusionsTree() {
    let tree = $('.ConclusionsTree');

    if (tree.length > 0)
        $.getJSON('conclusions', {format: 'json'}, PopulateConclusionsTree);
}

function PopulateConclusionsTree(data) {
    let tree = $('.ConclusionsTree');
    let ul = $('<ul>').appendTo(tree);
    let levels = new Map();

    data.forEach(entry => {
        if (!entry.abnormal)
            return;
        if (!levels.has(entry.level))
            levels.set(entry.level, new Array());
        entry.results.forEach(result => levels.get(entry.level).push(result));
    });

    let issues = ['critical', 'error', 'warning'];
    let info = ['info'];

    issues.concat(info).forEach(level => {
        if (levels.has(level)) {
            let li = $('<li>').text(level[0].toUpperCase() + level.slice(1) + 's').appendTo(ul);
            let sublist = $('<ul>').appendTo(li);
            if (issues.includes(level))
                li.addClass('jstree-open');
            levels.get(level).forEach(result => $('<li>').text(result).appendTo(sublist));
        }
    });

    tree.jstree({
        'core': {
            'themes': {
                'icons': false,
            },
        },
    });
}
